"""Daily brief (Monday to Friday): today's arXiv announcements via RSS -> topic filter -> one-line
summaries (one LLM request per section) -> email to daily subscribers.

The weekly edition (run_digest.py) stays on the arXiv API with full-text reports; the brief only needs
the RSS feed, which is a single request and reliable from GitHub's runners.

Usage: python run_brief.py [--dry-run] [--no-llm] [--force] [--per-section N]
Exit codes: 0 ok / nothing announced today, 2 SMTP missing, 3 send failed, 4 feed unreachable.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import arxiv_categories
import arxiv_client
import config
import email_builder
import mailer
from llm import LLM
from run_digest import EXIT_NO_PAPERS, subscriber_emails
from summarizer import Summarizer, rank, topic_matches

BRIEFS_DIR = os.path.join(config.DATA_DIR, "briefs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and send the Rinfo daily brief")
    parser.add_argument("--dry-run", action="store_true", help="build files but do not send email")
    parser.add_argument("--no-llm", action="store_true", help="abstract-based summaries only")
    parser.add_argument("--force", action="store_true", help="rebuild/resend even if today's brief exists")
    parser.add_argument("--per-section", type=int, default=config.env_int("DAILY_PER_SECTION", 5),
                        help="papers per section (default 5)")
    return parser.parse_args()


def select(papers: list[dict], per_section: int) -> list[dict]:
    """Papers for each section: in its categories, matching its topic filter, ranked by keywords."""
    sections, used = [], set()
    for domain in config.DOMAINS:
        cats = set(domain["categories"])
        matching = [p for p in papers if cats & set(p["categories"])
                    and topic_matches(domain.get("topic_query", ""), f"{p['title']} {p['abstract']}")]
        picked = rank(matching, domain["keywords"], exclude=used)[:per_section]
        used.update(p["id"] for p in picked)
        print(f"[{domain['key']}] {len(matching)} matched the topic filter, {len(picked)} selected")
        sections.append({"domain": domain, "papers": picked})
    return sections


def already_sent(path: str) -> bool:
    try:
        with open(path, encoding="utf-8") as fh:
            return bool(json.load(fh).get("sent"))
    except (OSError, ValueError):
        return False


def save_json(path: str, sections: list[dict], meta: dict, sent: bool) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({**brief_data(sections, meta), "sent": sent}, fh, ensure_ascii=False, indent=1)


def brief_data(sections: list[dict], meta: dict) -> dict:
    fields = ("id", "title", "abstract", "authors", "categories", "abs_url", "pdf_url", "published",
              "summary", "announce_type")
    return {
        "date": meta["date"], "issued": meta["issued"].isoformat(), "total": meta["total"],
        "sections": [{"key": s["domain"]["key"], "title": s["domain"]["title"],
                      "name": arxiv_categories.NAMES.get(s["domain"]["key"], s["domain"]["title"]),
                      "focus": s["domain"]["focus"], "lede": s.get("lede", ""),
                      "papers": [{k: p.get(k) for k in fields} for p in s["papers"]]} for s in sections],
    }


def main() -> int:
    args = parse_args()
    if not args.dry_run and mailer.missing_settings():
        print("ERROR: SMTP is not configured; missing " + ", ".join(mailer.missing_settings()), file=sys.stderr)
        return 2

    categories = sorted({c for d in config.DOMAINS for c in d["categories"]})
    try:
        feed_date, papers = arxiv_client.rss_announcements(categories)
    except Exception as exc:
        print(f"ERROR: could not read the arXiv RSS feed: {exc}", file=sys.stderr)
        return EXIT_NO_PAPERS
    if not papers:
        print("[rss] no announcement today (arXiv doesn't announce on weekends and holidays). Nothing to send.")
        return 0

    now = datetime.now(timezone.utc)
    date = feed_date or f"{now:%Y-%m-%d}"
    base = os.path.join(BRIEFS_DIR, date)
    if already_sent(base + ".json") and not args.force and not args.dry_run:
        print(f"[brief] the brief for {date} was already sent. Use --force to send it again.")
        return 0
    print(f"[rss] {len(papers)} new or cross-listed announcements on {date}")
    for p in papers:
        p["published"] = date

    sections = select(papers, max(1, min(args.per_section, 10)))
    summarizer = Summarizer(None if args.no_llm else LLM(max_calls=2 * len(sections)))
    for s in sections:
        result = summarizer.brief(s["domain"], s["papers"])
        s["lede"] = result["lede"]
        for p in s["papers"]:
            p["summary"] = result["summaries"].get(p["id"], "")
    picked = sum(len(s["papers"]) for s in sections)
    if picked == 0:
        print("[brief] nothing matched any section today. Nothing to send.")
        return 0

    meta = {"date": date, "issued": now, "total": len(papers)}
    html = email_builder.build_brief_html(sections, meta)
    text = email_builder.build_brief_text(sections, meta)
    os.makedirs(BRIEFS_DIR, exist_ok=True)
    os.makedirs(config.OUT_DIR, exist_ok=True)
    for path in (base + ".html", os.path.join(config.OUT_DIR, "brief-latest.html")):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
    print(f"[saved] {base}.html ({len(html.encode()) // 1024} KB)")

    if args.dry_run:
        save_json(base + ".json", sections, meta, sent=False)
        print("[dry-run] email not sent. Open out/brief-latest.html to preview.")
        return 0
    recipients = list(dict.fromkeys(a.lower() for a in config.MAIL_TO + subscriber_emails("daily")))
    subject = (f"Rinfo Daily Brief — {datetime.fromisoformat(date):%A %-d %B}: "
               f"{picked} new preprint{'s' if picked != 1 else ''}")
    try:
        failed = mailer.send(subject, html, text, recipients)
    except Exception as exc:
        print(f"ERROR: sending email failed: {exc}", file=sys.stderr)
        return 3
    save_json(base + ".json", sections, meta, sent=True)   # marks the day as done (and feeds the website)
    print(f"[sent] {len(recipients) - len(failed)} of {len(recipients)} recipients"
          + (f" ({len(failed)} failed)" if failed else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
