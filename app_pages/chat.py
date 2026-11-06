"""Chat page: talk to any arXiv paper, grounded in its PDF text (deep link: ?paper=<arxiv id>)."""
import json
import os
from datetime import datetime, timedelta, timezone

import openai
import streamlit as st

import arxiv_categories
import arxiv_client
import config
from llm import LLM
from tavily_client import WebSearch

HISTORY_MESSAGES = 8
QUICK_PROMPTS = {
    "Explain simply": "Explain this paper simply, as if to a final-year CS student.",
    "Key contributions": "What are the key contributions of this paper?",
    "Limitations": "What are the limitations and open questions of this paper?",
    "Reuse in my project": "How could I reuse the ideas or code from this paper in my own project?",
}
SYSTEM_PROMPT = """You are a helpful research assistant. Answer questions about ONE paper.
Rules:
- Answer only from the PAPER TEXT below. If the answer is not in it, say so plainly.
- Never invent numbers or results. Be concise and explain jargon briefly.
- If a WEB RESULTS block is given, you may use it, but mark every web-derived claim with [web]
  and keep it separate from facts taken from the paper.

PAPER TITLE: {title}
AUTHORS: {authors}

ABSTRACT:
{abstract}

PAPER TEXT (excerpt):
{excerpt}"""

# --- cached data -------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_digest(mtime: float) -> dict:
    """Read data/latest.json (mtime in the key busts the cache when the file changes)."""
    with open(config.LATEST_JSON, encoding="utf-8") as fh:
        return json.load(fh)


@st.cache_data(show_spinner="Looking up the paper on arXiv…", ttl=86400)
def fetch_paper(paper_id: str) -> dict | None:
    return arxiv_client.fetch_by_id(paper_id, attempts=2)


@st.cache_data(show_spinner="Downloading the preprint from arXiv…", ttl=86400, max_entries=20)
def fetch_pdf(pdf_url: str) -> bytes:
    """Official preprint PDF bytes (b'' on failure); reused for the excerpt and the download button."""
    try:
        return arxiv_client.download_pdf(pdf_url)
    except Exception as exc:
        print(f"  ! PDF download failed ({pdf_url}): {exc}")
        return b""


@st.cache_data(show_spinner="Reading the PDF…", ttl=86400)
def fetch_excerpt(pdf_url: str) -> str:
    data = fetch_pdf(pdf_url)
    if not data:
        return ""
    try:
        return arxiv_client.make_excerpt(arxiv_client.text_from_pdf(data), config.CHAT_CONTEXT_CHARS)
    except Exception as exc:
        print(f"  ! PDF text extraction failed ({pdf_url}): {exc}")
        return ""


@st.cache_resource
def get_llm() -> LLM:
    return LLM(delay=0)


@st.cache_resource
def get_web() -> WebSearch:
    return WebSearch(max_calls=10**9)


def digest_papers() -> dict[str, dict]:
    if not os.path.exists(config.LATEST_JSON):
        return {}
    try:
        data = load_digest(os.path.getmtime(config.LATEST_JSON))
    except (OSError, json.JSONDecodeError):
        return {}
    return {p["id"]: p for p in data.get("papers", [])}


def friendly_error(exc: Exception) -> str:
    if isinstance(exc, openai.RateLimitError):
        return "The LLM is rate-limited right now (free-tier quota). Wait a minute and try again."
    if isinstance(exc, openai.AuthenticationError):
        return "The LLM rejected the API key. Check LLM_API_KEY in your secrets."
    if isinstance(exc, openai.NotFoundError):
        return "Model not found. Run `python llm.py --list-models` and update LLM_MODEL."
    return f"The LLM request failed ({type(exc).__name__}). Please try again."


# --- sidebar / paper selection ---------------------------------------------------------
SOURCE_DIGEST, SOURCE_LIVE = "This week's digest", "Latest on arXiv"
ALL = "all"


@st.cache_data(show_spinner="Fetching the latest preprints from arXiv…", ttl=1800)
def live_papers(code: str, days: int, keywords: str, limit: int) -> list[dict]:
    """Newest preprints in one official arXiv category, straight from the arXiv API."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return arxiv_client.search_category(code, cutoff, keywords=keywords, max_results=limit, attempts=2)


def paper_categories(p: dict) -> list[str]:
    return p.get("categories") or [p.get("category", "")]


digest = digest_papers()
ss = st.session_state
if "paper_id" not in ss:
    ss.paper_id = arxiv_client.normalize_id(st.query_params.get("paper", ""))
if "histories" not in ss:
    ss.histories = {}

with st.sidebar:
    st.title("📡 Research Radar")
    source = st.radio("Papers from", [SOURCE_DIGEST, SOURCE_LIVE], key="source", horizontal=True)
    if source == SOURCE_DIGEST:
        # Only the official categories that actually occur in the digest, with counts.
        counts: dict[str, int] = {}
        for p in digest.values():
            for code in paper_categories(p):
                counts[code] = counts.get(code, 0) + 1
        codes = [ALL] + sorted(counts, key=lambda c: (-counts[c], c))
        category = st.selectbox(
            "arXiv category", codes, key="digest_category",
            format_func=lambda c: f"All categories ({len(digest)})" if c == ALL
            else f"{arxiv_categories.label(c)} ({counts[c]})")
    else:
        category = st.selectbox("arXiv category", arxiv_categories.ordered_codes(), key="live_category",
                                format_func=arxiv_categories.label,
                                help="Official arXiv taxonomy. Type to search, e.g. 'eess' or 'Machine'.")
        st.caption(f"Group: {arxiv_categories.GROUP_OF.get(category, '')} · "
                   f"[browse on arXiv](https://arxiv.org/list/{category}/recent)")
        keywords = st.text_input("Keywords (optional)", key="live_keywords",
                                 placeholder="e.g. state of health, dialogue, quantization")
        c1, c2 = st.columns(2)
        days = c1.slider("Look back (days)", 1, 30, config.DAYS_BACK, key="days")
        limit = c2.select_slider("Max papers", [10, 25, config.MAX_PAPERS], value=25, key="limit")

# Papers shown in the dropdown, filtered by source and official category.
listed: dict[str, dict] = {}
if source == SOURCE_DIGEST:
    listed = {pid: p for pid, p in digest.items() if category == ALL or category in paper_categories(p)}
else:
    try:
        listed = {p["id"]: p for p in live_papers(category, days, keywords.strip(), limit)}
    except Exception as exc:
        st.sidebar.error(f"arXiv request failed: {exc}")

options = [""] + list(listed)
if "pick" not in ss or ss.pick not in options:
    ss.pick = ss.paper_id if ss.paper_id in listed else ""


def on_pick():
    if ss.pick:
        ss.paper_id = ss.pick


def on_manual():
    pid = arxiv_client.normalize_id(ss.manual)
    if pid:
        ss.paper_id = pid
        ss.pick = pid if pid in listed else ""
    elif ss.manual.strip():
        st.sidebar.warning("That doesn't look like an arXiv id or URL.")


def label(pid: str) -> str:
    if not pid:
        return f"— choose one of {len(listed)} papers —" if listed else "— no papers here —"
    p = listed[pid]
    star = "⭐ " if p.get("featured") else ""
    tag = f"[{p.get('category', '')}] " if category == ALL else ""
    return f"{star}{tag}{p['title'][:70]} ({p.get('published', '')[:10]})"


with st.sidebar:
    st.selectbox("Paper", options, format_func=label, key="pick", on_change=on_pick)
    if not listed:
        st.caption("No papers here yet. Run `python run_digest.py --dry-run`, or switch to "
                   "“Latest on arXiv”." if source == SOURCE_DIGEST
                   else "No preprints found. Try more days, another category or fewer keywords.")
    st.text_input("…or any arXiv id / URL", key="manual", on_change=on_manual,
                  placeholder="2401.01234, arXiv:2401.01234v2, https://arxiv.org/abs/…")
    use_web = st.checkbox("Search the web with Tavily", value=False,
                          disabled=not config.TAVILY_API_KEY,
                          help=None if config.TAVILY_API_KEY else "Set TAVILY_API_KEY to enable.")
    if st.button("Clear chat", use_container_width=True) and ss.paper_id:
        ss.histories.pop(ss.paper_id, None)

paper_id = ss.paper_id
if not paper_id:
    st.header("Chat with a paper")
    st.info("Pick a paper from the sidebar, paste an arXiv id/URL, or open a link from your digest email.")
    st.stop()
if st.query_params.get("paper") != paper_id:
    st.query_params["paper"] = paper_id

# --- paper header ------------------------------------------------------------------------
digest_entry = digest.get(paper_id)
try:
    paper = digest_entry or listed.get(paper_id) or fetch_paper(paper_id)
except Exception as exc:
    st.error(f"Could not reach arXiv: {exc}")
    st.stop()
if not paper:
    st.error(f"No arXiv paper found for id `{paper_id}`.")
    st.stop()

st.header(paper["title"])
authors = paper.get("authors", [])
st.caption(", ".join(authors[:10]) + (" et al." if len(authors) > 10 else ""))
cats = paper_categories(paper)
st.markdown(" ".join(f"`{c}`" for c in cats) + f" &nbsp; {arxiv_categories.NAMES.get(cats[0], '')}"
            f" · arXiv:{paper_id} · submitted {paper.get('published', '')[:10]}")

# Official preprint: open on arXiv, open the PDF, or download it.
pdf_bytes = fetch_pdf(paper["pdf_url"])
b1, b2, b3 = st.columns(3)
b1.link_button("🔗 arXiv abstract page", paper["abs_url"], use_container_width=True)
b2.link_button("📄 Open official PDF", paper["pdf_url"], use_container_width=True)
if pdf_bytes:
    b3.download_button("⬇️ Download preprint", pdf_bytes, file_name=f"arXiv-{paper_id}.pdf",
                       mime="application/pdf", use_container_width=True)
else:
    b3.button("⬇️ PDF unavailable", disabled=True, use_container_width=True)
with st.expander("Abstract", expanded=not (digest_entry or {}).get("insight")):
    st.write(paper.get("abstract", ""))
insight = (digest_entry or {}).get("insight")
if insight:
    with st.expander("Digest summary", expanded=False):
        st.markdown(f"**TL;DR** {insight.get('tldr', '')}")
        for key, name in [("problem", "Problem"), ("approach", "Approach")]:
            st.markdown(f"**{name}.** {insight.get(key, '')}")
        st.markdown("**Key findings**\n" + "\n".join(f"- {f}" for f in insight.get("key_findings", [])))
        st.markdown(f"**Limitations.** {insight.get('limitations', '')}")
        st.markdown(f"**Why it matters.** {insight.get('why_it_matters', '')}")
        st.caption("LLM-generated summary; check the paper.")

excerpt = fetch_excerpt(paper["pdf_url"])
if not excerpt:
    st.warning("Couldn't read the PDF, so answers will use the abstract only.")

# --- chat ---------------------------------------------------------------------------------
history = ss.histories.setdefault(paper_id, [])


def show_sources(sources: list[dict]):
    if sources:
        st.caption("Web sources: " + " · ".join(f"[{s['host'] or s['title']}]({s['url']})" for s in sources))


for msg in history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        show_sources(msg.get("sources", []))

clicked = None
cols = st.columns(len(QUICK_PROMPTS))
for col, (name, text) in zip(cols, QUICK_PROMPTS.items()):
    if col.button(name, use_container_width=True):
        clicked = text
typed = st.chat_input("Ask anything about this paper…")
prompt = clicked or typed

if prompt:
    history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        sources = []
        if use_web:
            with st.spinner("Searching the web…"):
                sources = get_web().search(f"{paper['title']} {prompt}", 4)
        system = SYSTEM_PROMPT.format(title=paper["title"], authors=", ".join(authors[:10]),
                                      abstract=paper.get("abstract", ""),
                                      excerpt=excerpt or "(PDF text unavailable; use the abstract only.)")
        turns = [{"role": m["role"], "content": m["content"]} for m in history[-HISTORY_MESSAGES:]]
        if sources:
            web_block = "\n\n".join(f"[{i}] {s['title']} ({s['url']})\n{s['snippet']}"
                                    for i, s in enumerate(sources, 1))
            turns[-1]["content"] += ("\n\n=== WEB RESULTS (not from the paper; mark claims from here "
                                     f"with [web]) ===\n{web_block}\n=== END WEB RESULTS ===")
        try:
            answer = st.write_stream(get_llm().stream([{"role": "system", "content": system}] + turns))
        except Exception as exc:
            history.pop()  # drop the failed user turn so a retry starts clean
            st.error(friendly_error(exc))
        else:
            show_sources(sources)
            history.append({"role": "assistant", "content": answer if isinstance(answer, str) else str(answer),
                            "sources": sources})
