"""Weekly pipeline: arXiv -> rank -> PDF excerpt -> LLM insight -> Tavily -> email.

Usage: python run_digest.py [--dry-run] [--no-llm] [--no-fulltext] [--no-web] [--days N]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import arxiv_client
import config
import email_builder
import mailer
from llm import LLM
from summarizer import Summarizer, fallback_insight, rank
from tavily_client import WebSearch

EXIT_NO_PAPERS = 4   # distinct code so CI can safely retry (nothing was sent)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and send the Research Radar digest")
    parser.add_argument("--dry-run", action="store_true", help="build files but do not send email")
    parser.add_argument("--no-llm", action="store_true", help="use abstract-based summaries only")
    parser.add_argument("--no-fulltext", action="store_true", help="skip PDF download")
    parser.add_argument("--no-web", action="store_true", help="skip Tavily enrichment")
    parser.add_argument("--days", type=int, default=config.DAYS_BACK, help="look-back window in days")
    return parser.parse_args()


def collect(cutoff: datetime) -> tuple[list[dict], int]:
    """Fetch and rank papers per domain; returns sections and the scanned count."""
    sections, used, scanned = [], set(), 0
    for domain in config.DOMAINS:
        print(f"[arXiv] {domain['title']}")
        try:
            papers = arxiv_client.search(domain["query"], cutoff)
        except Exception as exc:
            print(f"  ! arXiv search failed: {exc}")
            papers = []
        scanned += len(papers)
        ranked = rank(papers, domain["keywords"], exclude=used)
        featured = ranked[:config.FEATURED_PER_DOMAIN]
        more = ranked[config.FEATURED_PER_DOMAIN:config.FEATURED_PER_DOMAIN + config.MORE_LINKS_PER_DOMAIN]
        used.update(p["id"] for p in featured + more)
        print(f"  {len(papers)} found, {len(featured)} featured, {len(more)} more")
        sections.append({"domain": domain, "featured": featured, "more": more})
    return sections, scanned


def enrich(sections: list[dict], args: argparse.Namespace) -> None:
    """Add PDF-grounded insights, overviews and web links. Never raises per paper."""
    summarizer = Summarizer(None if args.no_llm else LLM(max_calls=config.LLM_MAX_CALLS_PER_RUN))
    web = WebSearch(enabled=not args.no_web)
    for s in sections:
        d = s["domain"]
        for p in s["featured"]:
            print(f"[paper] {p['id']} {p['title'][:70]}")
            try:
                excerpt = "" if args.no_fulltext else arxiv_client.pdf_excerpt(p["pdf_url"], config.DIGEST_CONTEXT_CHARS)
                p["insight"] = summarizer.insight(p, d, excerpt)
                p["links"] = web.code_links(p["title"])
            except Exception as exc:  # one bad paper must not sink the run
                print(f"  ! failed: {exc}")
                p.setdefault("insight", fallback_insight(p, d))
                p.setdefault("links", [])
        s["overview"] = summarizer.overview(d, s["featured"], s["more"])
        s["beyond"] = web.beyond_arxiv(d)
    llm_calls = summarizer.llm.calls if summarizer.llm else 0
    print(f"[usage] LLM requests: {llm_calls}, Tavily searches: {web.calls}")


def save(sections: list[dict], meta: dict, html: str, now: datetime) -> str:
    """Write out/latest.html, out/digest-YYYY-MM-DD.html and data/latest.json."""
    os.makedirs(config.OUT_DIR, exist_ok=True)
    os.makedirs(config.DATA_DIR, exist_ok=True)
    latest = os.path.join(config.OUT_DIR, "latest.html")
    for path in (latest, os.path.join(config.OUT_DIR, f"digest-{now:%Y-%m-%d}.html")):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
    papers = []
    for s in sections:
        d = s["domain"]
        for featured, group in ((True, s["featured"]), (False, s["more"])):
            for p in group:
                papers.append({**p, "domain": d["key"], "domain_title": d["title"], "featured": featured,
                               "insight": p.get("insight"), "links": p.get("links", [])})
    data = {
        "generated_at": now.isoformat(),
        "week_range": meta["week_range"],
        "scanned": meta["scanned"],
        "overviews": {s["domain"]["key"]: s.get("overview", "") for s in sections},
        "beyond_arxiv": {s["domain"]["key"]: s.get("beyond", []) for s in sections},
        "papers": papers,
    }
    with open(config.LATEST_JSON, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return latest


def main() -> int:
    args = parse_args()
    if not args.dry_run and mailer.missing_settings():
        print("ERROR: SMTP is not configured; missing " + ", ".join(mailer.missing_settings()) +
              ". Set them in .env / GitHub secrets, or use --dry-run.", file=sys.stderr)
        return 2

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=args.days)
    sections, scanned = collect(cutoff)
    picked = sum(len(s["featured"]) + len(s["more"]) for s in sections)
    if picked == 0:
        print(f"ERROR: no papers found in the last {args.days} days for any domain "
              "(arXiv may be rate-limiting this machine; see the '!' lines above).", file=sys.stderr)
        return EXIT_NO_PAPERS

    enrich(sections, args)
    meta = {"week_range": f"{cutoff:%d %b} – {now:%d %b %Y}", "scanned": scanned, "picked": picked,
            "issued": now}
    html = email_builder.build_html(sections, meta)
    text = email_builder.build_text(sections, meta)
    path = save(sections, meta, html, now)
    print(f"[saved] {path} and {config.LATEST_JSON}")

    if args.dry_run:
        print("[dry-run] email not sent. Open out/latest.html in a browser to preview.")
        return 0
    subject = (f"The Research Radar — Weekly Edition No. {now.isocalendar().week}, "
               f"{now:%d %B %Y}: {picked} preprints")
    try:
        mailer.send(subject, html, text)
    except Exception as exc:
        print(f"ERROR: sending email failed: {exc}", file=sys.stderr)
        return 3
    print(f"[sent] to {', '.join(config.MAIL_TO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
