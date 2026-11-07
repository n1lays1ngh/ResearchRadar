"""Rinfo API (FastAPI), deployed as a Vercel Python function at /api/*.

Local:  uvicorn api.index:app --reload --port 8000     (the Vite dev server proxies /api here)

Endpoints
  GET  /api/health
  GET  /api/categories                     official arXiv taxonomy
  GET  /api/paper/{id}                     metadata for any arXiv paper
  GET  /api/arxiv?category=&days=&q=&limit=  newest preprints in a category
  POST /api/chat                           stream an answer about one paper (NDJSON)
  POST /api/subscribe                      email a confirmation link
  POST /api/subscribe/confirm              apply a confirmation link
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import openai  # noqa: E402
from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

import arxiv_categories  # noqa: E402
import arxiv_client  # noqa: E402
import config  # noqa: E402
import mailer  # noqa: E402
import subscribers  # noqa: E402
from llm import LLM  # noqa: E402
from tavily_client import WebSearch  # noqa: E402

app = FastAPI(title="Rinfo API", docs_url="/api/docs", openapi_url="/api/openapi.json")

CACHE_DIR = "/tmp/rinfo"   # the only writable place on Vercel; survives warm invocations
HISTORY_MESSAGES = 8
SYSTEM_PROMPT = """You are the research desk of a quality newspaper, answering a reader's questions about ONE paper.
Rules:
- Answer only from the PAPER TEXT below. If the answer is not in it, say so plainly.
- Never invent numbers or results. Be concise, write clearly and explain jargon briefly.
- If a WEB RESULTS block is given, you may use it, but mark every web-derived claim with [web]
  and keep it separate from facts taken from the paper.

PAPER TITLE: {title}
AUTHORS: {authors}

ABSTRACT:
{abstract}

PAPER TEXT (excerpt):
{excerpt}"""


# --- helpers ---------------------------------------------------------------------------
def _paper_id(raw: str) -> str:
    pid = arxiv_client.normalize_id(raw)
    if not pid:
        raise HTTPException(400, "That doesn't look like an arXiv id or URL.")
    return pid


@lru_cache(maxsize=256)
def _fetch_paper(pid: str) -> dict | None:
    return arxiv_client.fetch_by_id(pid, attempts=2)


def _excerpt(pid: str) -> str:
    """PDF text excerpt for the chat context, cached in /tmp ('' if the PDF can't be read)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, pid.replace("/", "_") + ".txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    try:
        data = arxiv_client.download_pdf(f"https://arxiv.org/pdf/{pid}")
        text = arxiv_client.make_excerpt(arxiv_client.text_from_pdf(data), config.CHAT_CONTEXT_CHARS)
    except Exception as exc:
        print(f"  ! PDF read failed for {pid}: {exc}")
        return ""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text


def _friendly(exc: Exception) -> str:
    if isinstance(exc, openai.RateLimitError):
        return "The language model is rate-limited right now (free-tier quota). Please wait a minute."
    if isinstance(exc, openai.AuthenticationError):
        return "The language model rejected the API key. Check LLM_API_KEY on the server."
    if isinstance(exc, openai.NotFoundError):
        return "Model not found. Check LLM_MODEL on the server."
    return f"The request failed ({type(exc).__name__}). Please try again."


# --- read-only endpoints -------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "llm": bool(config.LLM_API_KEY), "web": bool(config.TAVILY_API_KEY),
            "subscriptions": not (subscribers.missing_settings() or mailer.missing_settings(False))}


@app.get("/api/categories")
def categories():
    return {"groups": [{"name": g, "categories": [{"code": c, "name": n} for c, n in cats.items()]}
                       for g, cats in arxiv_categories.GROUPS.items()],
            "suggested": list(arxiv_categories.SUGGESTED)}


@app.get("/api/paper/{raw_id:path}")
def paper(raw_id: str):
    pid = _paper_id(raw_id)
    try:
        found = _fetch_paper(pid)
    except Exception as exc:
        raise HTTPException(502, f"arXiv could not be reached ({type(exc).__name__}). Try again shortly.")
    if not found:
        raise HTTPException(404, f"No arXiv paper found for {pid}.")
    return found


@app.get("/api/arxiv")
def latest(category: str, days: int = 7, q: str = "", limit: int = 25):
    if category not in arxiv_categories.NAMES:
        raise HTTPException(400, "Unknown arXiv category.")
    days, limit = max(1, min(days, 30)), max(1, min(limit, config.MAX_PAPERS))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    try:
        papers = arxiv_client.search_category(category, cutoff, keywords=q[:200], max_results=limit, attempts=2)
    except Exception as exc:
        raise HTTPException(502, f"arXiv could not be reached ({type(exc).__name__}). Try again shortly.")
    return {"category": category, "name": arxiv_categories.NAMES[category], "papers": papers}


# --- chat ------------------------------------------------------------------------------------
class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class PaperIn(BaseModel):
    id: str
    title: str = Field("", max_length=600)
    authors: list[str] = Field(default_factory=list, max_length=200)
    abstract: str = Field("", max_length=6000)


class ChatIn(BaseModel):
    paper: PaperIn
    messages: list[Turn] = Field(min_length=1, max_length=40)
    web: bool = False


@app.post("/api/chat")
def chat(body: ChatIn):
    """Streams NDJSON lines: {"type":"sources"|"delta"|"error"|"done", ...}."""
    pid = _paper_id(body.paper.id)
    if body.messages[-1].role != "user":
        raise HTTPException(400, "The last message must be from the user.")
    if not config.LLM_API_KEY:
        raise HTTPException(503, "Chat is not configured on the server (LLM_API_KEY).")

    def events():
        def line(obj):
            return json.dumps(obj) + "\n"
        try:
            excerpt = _excerpt(pid)
            sources = []
            question = body.messages[-1].content
            if body.web and config.TAVILY_API_KEY:
                sources = WebSearch(max_calls=1).search(f"{body.paper.title} {question}", 4)
            yield line({"type": "sources", "sources": sources, "fulltext": bool(excerpt)})
            authors = ", ".join(body.paper.authors[:10])
            system = SYSTEM_PROMPT.format(title=body.paper.title, authors=authors, abstract=body.paper.abstract,
                                          excerpt=excerpt or "(PDF text unavailable; use the abstract only.)")
            turns = [t.model_dump() for t in body.messages[-HISTORY_MESSAGES:]]
            if sources:
                block = "\n\n".join(f"[{i}] {s['title']} ({s['url']})\n{s['snippet']}"
                                    for i, s in enumerate(sources, 1))
                turns[-1]["content"] += ("\n\n=== WEB RESULTS (not from the paper; mark claims from here "
                                         f"with [web]) ===\n{block}\n=== END WEB RESULTS ===")
            for piece in LLM(delay=0).stream([{"role": "system", "content": system}] + turns):
                yield line({"type": "delta", "text": piece})
            yield line({"type": "done"})
        except Exception as exc:
            print(f"  ! chat failed: {type(exc).__name__}: {exc}")
            yield line({"type": "error", "message": _friendly(exc)})

    return StreamingResponse(events(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# --- subscriptions (double opt-in by emailed link) -------------------------------------------
_recent: dict[str, float] = {}   # best-effort per-instance throttle: address -> last link sent
RESEND_GAP = 60


class SubscribeIn(BaseModel):
    email: str = Field(max_length=254)
    action: Literal["subscribe", "unsubscribe"] = "subscribe"
    lists: list[Literal["weekly", "daily"]] = Field(default_factory=lambda: ["weekly"], max_length=2)
    website: str = ""   # honeypot: real visitors never fill this hidden field


class ConfirmIn(BaseModel):
    token: str = Field(max_length=2000)


def _require_subscriptions():
    missing = mailer.missing_settings(need_recipients=False) + subscribers.missing_settings()
    if missing:
        print("  ! subscriptions not configured; missing " + ", ".join(missing))
        raise HTTPException(503, "Subscriptions aren't available right now.")


@app.post("/api/subscribe")
def subscribe(body: SubscribeIn, request: Request):
    _require_subscriptions()
    if body.website:
        return {"ok": True, "message": "Check your inbox for a confirmation link."}
    email = subscribers.normalize_email(body.email)
    if not email:
        raise HTTPException(400, "Please enter a valid email address.")
    now = time.time()
    if now - _recent.get(email, 0) < RESEND_GAP:
        raise HTTPException(429, "A confirmation link was just sent. Please check your inbox.")
    base = config.SITE_URL.rstrip("/") if config.SITE_URL else str(request.base_url).rstrip("/")
    lists = subscribers.normalize_lists(body.lists)
    url = f"{base}/confirm?token={subscribers.make_token(email, body.action, lists)}"
    try:
        mailer.send_confirm_link(email, body.action, url, lists)
    except Exception as exc:
        print(f"  ! confirmation email failed: {type(exc).__name__}: {exc}")
        raise HTTPException(502, "We couldn't send the confirmation email. Please try again later.")
    _recent[email] = now
    return {"ok": True, "message": f"We've sent a confirmation link to {email}. It works for 24 hours."}


@app.post("/api/subscribe/confirm")
def confirm(body: ConfirmIn):
    _require_subscriptions()
    try:
        email, action, lists = subscribers.read_token(body.token)
    except subscribers.SubscribersError as exc:
        raise HTTPException(400, str(exc))
    try:
        if action == "subscribe":
            outcome = subscribers.add(email, lists)
            what = _describe(lists)
            msg = {"added": f"You're subscribed to {what}.",
                   "updated": f"Your preferences are saved: you'll now get {what}.",
                   "unchanged": f"You're already subscribed to {what}."}[outcome]
        else:
            changed = subscribers.remove(email)
            msg = "You've been unsubscribed." if changed else "That address wasn't subscribed."
    except Exception as exc:
        print(f"  ! subscriber update failed: {type(exc).__name__}: {exc}")
        raise HTTPException(502, "We couldn't update the subscriber list. Please try again later.")
    return {"ok": True, "action": action, "email": email, "lists": lists, "message": msg}


def _describe(lists: list[str]) -> str:
    names = {"weekly": "the weekly edition (Sundays)",
             "daily": "the daily brief (Monday to Friday, plus a Saturday week in review)"}
    return " and ".join(names[name] for name in lists)
