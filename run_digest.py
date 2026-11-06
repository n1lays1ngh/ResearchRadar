"""Weekly pipeline: arXiv -> rank -> PDF excerpt -> LLM insight -> Tavily -> email.

Usage: python run_digest.py [--dry-run] [--no-llm] [--no-fulltext] [--no-web] [--days N]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import arxiv_categories
import arxiv_client
import config
import email_builder
import mailer
import pdf_export
import subscribers
from llm import LLM
from summarizer import Summarizer, fallback_insight, rank
from tavily_client import WebSearch

EXIT_NO_PAPERS = 4   # distinct code so CI can safely retry (nothing was sent)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and send the Rinfo weekly edition")
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


PAPER_FIELDS = ("id", "title", "abstract", "authors", "published", "categories", "abs_url", "pdf_url",
                "insight", "links")


def edition_data(sections: list[dict], meta: dict, now: datetime) -> dict:
    """Everything the website needs to render one edition (data/editions/YYYY-MM-DD.json)."""
    vol, _ = email_builder._edition({"issued": now})
    out = {"date": f"{now:%Y-%m-%d}", "issued": now.isoformat(), "edition": vol,
           "week_range": meta["week_range"], "scanned": meta["scanned"], "picked": meta["picked"],
           "sections": []}
    for s in sections:
        d = s["domain"]
        out["sections"].append({
            "key": d["key"], "title": d["title"], "name": arxiv_categories.NAMES.get(d["key"], d["title"]),
            "focus": d["focus"], "categories": d["categories"],
            "overview": s.get("overview", ""), "beyond": s.get("beyond", []),
            "featured": [{k: p.get(k) for k in PAPER_FIELDS} for p in s["featured"]],
            "more": [{k: p.get(k) for k in PAPER_FIELDS} for p in s["more"]],
        })
    return out


def save(sections: list[dict], meta: dict, html: str, now: datetime) -> str:
    """Write out/latest.html, the archived edition (data/editions/YYYY-MM-DD.html/.json/.pdf)
    and data/latest.json. The website is built from data/editions/."""
    os.makedirs(config.OUT_DIR, exist_ok=True)
    os.makedirs(config.EDITIONS_DIR, exist_ok=True)
    latest = os.path.join(config.OUT_DIR, "latest.html")
    edition = os.path.join(config.EDITIONS_DIR, f"{now:%Y-%m-%d}")
    for path in (latest, os.path.join(config.OUT_DIR, f"digest-{now:%Y-%m-%d}.html"), edition + ".html"):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
    with open(edition + ".json", "w", encoding="utf-8") as fh:
        json.dump(edition_data(sections, meta, now), fh, ensure_ascii=False, indent=1)
    if pdf_export.html_to_pdf(html, edition + ".pdf"):
        print(f"[saved] {edition}.pdf")
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


def subscriber_emails(newsletter: str = "weekly") -> list[str]:
    """Subscribers to one newsletter; [] (with a warning) if not configured or unreachable."""
    if subscribers.missing_settings():
        print("[subscribers] not configured; sending to MAIL_TO only")
        return []
    try:
        found = subscribers.emails(newsletter)
    except Exception as exc:   # never skip the owner's copy because of the subscriber list
        print(f"  ! could not load subscribers: {exc}")
        return []
    print(f"[subscribers] {len(found)} {newsletter} subscriber(s)")
    return found


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
    recipients = list(dict.fromkeys(a.lower() for a in config.MAIL_TO + subscriber_emails()))
    subject = (f"Rinfo Weekly — No. {now.isocalendar().week}, "
               f"{now:%-d %B %Y}: {picked} preprints")
    try:
        failed = mailer.send(subject, html, text, recipients)
    except Exception as exc:
        print(f"ERROR: sending email failed: {exc}", file=sys.stderr)
        return 3
    # Counts only: Actions logs of a public repo are public, so never print addresses.
    print(f"[sent] {len(recipients) - len(failed)} of {len(recipients)} recipients"
          + (f" ({len(failed)} failed)" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
