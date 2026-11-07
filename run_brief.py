"""Daily brief for the daily list.

Monday to Friday: today's arXiv announcements via RSS -> topic filter -> one-line summaries (one LLM
request per section) -> email.
Saturday (arXiv announces nothing at weekends): the Week in Review, the best papers from this week's
saved briefs (data/briefs), re-ranked, with a fresh lede per section. No arXiv request at all.

The weekly edition (run_digest.py, Sundays) stays on the arXiv API with full-text reports.

Usage: python run_brief.py [--dry-run] [--no-llm] [--force] [--per-section N] [--review]
Exit codes: 0 ok / nothing to send, 2 SMTP missing, 3 send failed, 4 feed unreachable.
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
    parser.add_argument("--review", action="store_true",
                        help="build the Week in Review from this week's briefs (automatic on Saturdays)")
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


def week_in_review(today: datetime, per_section: int) -> tuple[list[dict], dict] | None:
    """Sections for Saturday's Week in Review from the briefs of the previous six days, or None."""
    days = [f"{today - timedelta(days=n):%Y-%m-%d}" for n in range(6, 0, -1)]
    pool, covered, total = {}, [], 0
    for day in days:
        try:
            with open(os.path.join(BRIEFS_DIR, day + ".json"), encoding="utf-8") as fh:
                brief = json.load(fh)
        except (OSError, ValueError):
            continue
        if brief.get("kind") == "review":
            continue
        covered.append(day)
        total += brief.get("total", 0)
        for s in brief["sections"]:
            for p in s["papers"]:
                pool.setdefault(s["key"], {}).setdefault(p["id"], p)
    if not covered:
        return None
    sections, used = [], set()
    for domain in config.DOMAINS:
        candidates = list(pool.get(domain["key"], {}).values())
        picked = rank(candidates, domain["keywords"], exclude=used)[:per_section]
        used.update(p["id"] for p in picked)
        print(f"[{domain['key']}] {len(candidates)} papers in this week's briefs, {len(picked)} selected")
        sections.append({"domain": domain, "papers": picked})
    return sections, {"covered": covered, "total": total}


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
    extra = {"kind": "review", "covered": meta["covered"]} if meta.get("kind") == "review" else {}
    return {
        "date": meta["date"], "issued": meta["issued"].isoformat(), "total": meta["total"], **extra,
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

    now = datetime.now(timezone.utc)
    per_section = max(1, min(args.per_section, 10))
    review = args.review or now.weekday() == 5   # Saturday
    if review:
        date = f"{now:%Y-%m-%d}"
        built = week_in_review(now, per_section)
        if not built:
            print("[review] no daily briefs saved this week. Nothing to send.")
            return 0
        sections, extra = built
        meta = {"date": date, "issued": now, "kind": "review", **extra}
        print(f"[review] {len(extra['covered'])} brief(s) this week: {', '.join(extra['covered'])}")
    else:
        categories = sorted({c for d in config.DOMAINS for c in d["categories"]})
        try:
            feed_date, papers = arxiv_client.rss_announcements(categories)
        except Exception as exc:
            print(f"ERROR: could not read the arXiv RSS feed: {exc}", file=sys.stderr)
            return EXIT_NO_PAPERS
        if not papers:
            print("[rss] no announcement today (arXiv doesn't announce on weekends and holidays). Nothing to send.")
            return 0
        date = feed_date or f"{now:%Y-%m-%d}"
        print(f"[rss] {len(papers)} new or cross-listed announcements on {date}")
        for p in papers:
            p["published"] = date
        sections = select(papers, per_section)
        meta = {"date": date, "issued": now, "total": len(papers)}

    base = os.path.join(BRIEFS_DIR, date)
    if already_sent(base + ".json") and not args.force and not args.dry_run:
        print(f"[brief] the brief for {date} was already sent. Use --force to send it again.")
        return 0

    summarizer = Summarizer(None if args.no_llm else LLM(max_calls=2 * len(sections)))
    for s in sections:
        result = summarizer.brief(s["domain"], s["papers"], "this week" if review else "today")
        s["lede"] = result["lede"]
        for p in s["papers"]:
            # the week in review keeps each paper's summary from its daily brief
            p["summary"] = (p.get("summary") if review else "") or result["summaries"].get(p["id"], "")
    picked = sum(len(s["papers"]) for s in sections)
    if picked == 0:
        print("[brief] nothing matched any section. Nothing to send.")
        return 0

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
    plural = "s" if picked != 1 else ""
    subject = (f"The Rinfo — Week in Review, {datetime.fromisoformat(date):%A %-d %B}: "
               f"the week's {picked} best preprint{plural}" if review else
               f"The Rinfo — Daily Brief, {datetime.fromisoformat(date):%A %-d %B}: {picked} new preprint{plural}")
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
