"""arXiv API search, single-paper lookup and PDF text excerpts."""
import io
import random
import re
import time
from datetime import datetime, timezone

import feedparser
import requests
from pypdf import PdfReader

import config

API_URL = "https://export.arxiv.org/api/query"
_last_request = 0.0

_ID_RE = re.compile(r"(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(v\d+)?", re.I)


def _retry_wait(resp: requests.Response | None, attempt: int) -> float:
    """Seconds to wait before the next try: arXiv's Retry-After if given, else exponential backoff."""
    header = resp.headers.get("Retry-After", "") if resp is not None else ""
    base = float(header) if header.isdigit() else config.ARXIV_BACKOFF_SECONDS * (2 ** attempt)
    return min(base, 120.0) + random.uniform(0, 3)


def _get(url: str, params: dict | None = None, timeout: int = 60,
         attempts: int = config.ARXIV_ATTEMPTS) -> requests.Response:
    """Polite GET: 3 s between requests, custom User-Agent, long backoff on 429/503/timeouts."""
    global _last_request
    last_error: Exception | None = None
    for attempt in range(attempts):
        wait = config.ARXIV_DELAY_SECONDS - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()
        resp = None
        try:
            resp = requests.get(url, params=params, timeout=(15, timeout),
                                headers={"User-Agent": config.USER_AGENT})
            if resp.status_code == 200:
                return resp
            last_error = RuntimeError(f"HTTP {resp.status_code} from {url}")
            if resp.status_code in (400, 404):      # not worth retrying
                break
        except requests.RequestException as exc:
            last_error = exc
        if attempt + 1 < attempts:
            pause = _retry_wait(resp, attempt)
            print(f"  · arXiv busy ({last_error}); retry {attempt + 2}/{attempts} in {pause:.0f}s")
            time.sleep(pause)
    raise last_error or RuntimeError(f"GET {url} failed")


def normalize_id(text: str) -> str:
    """Turn an arXiv URL, 'arXiv:' id or versioned id into a bare id like 2401.01234."""
    text = (text or "").strip()
    text = re.sub(r"^arxiv:\s*", "", text, flags=re.I)
    text = re.sub(r"\.pdf$", "", text, flags=re.I)
    match = _ID_RE.search(text)
    return match.group(1) if match else ""


def _parse_entry(entry) -> dict:
    """Convert a feedparser entry to our paper dict."""
    paper_id = normalize_id(entry.get("id", ""))
    published = entry.get("published", "")
    pdf_url = next((l.get("href") for l in entry.get("links", [])
                    if l.get("type") == "application/pdf" or l.get("title") == "pdf"), None)
    categories = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]
    category = (entry.get("arxiv_primary_category") or {}).get("term") or (categories or [""])[0]
    return {
        "id": paper_id,
        "title": " ".join(entry.get("title", "").split()),
        "abstract": " ".join(entry.get("summary", "").split()),
        "authors": [a.get("name", "") for a in entry.get("authors", [])],
        "published": published,
        "category": category,
        "categories": categories or [category],
        "abs_url": f"https://arxiv.org/abs/{paper_id}",
        "pdf_url": (pdf_url or f"https://arxiv.org/pdf/{paper_id}").replace("http://", "https://"),
    }


def _published_dt(paper: dict) -> datetime:
    try:
        return datetime.fromisoformat(paper["published"].replace("Z", "+00:00"))
    except (ValueError, KeyError):
        return datetime.now(timezone.utc)


def search(query: str, cutoff: datetime, max_results: int = config.MAX_RESULTS_PER_DOMAIN,
           attempts: int = config.ARXIV_ATTEMPTS) -> list[dict]:
    """Newest-first search that stops at the cutoff date or max_results (never above MAX_PAPERS)."""
    max_results = max(1, min(max_results, config.MAX_PAPERS))
    papers: list[dict] = []
    start = 0
    while start < max_results:
        params = {
            "search_query": query,
            "start": start,
            "max_results": min(config.ARXIV_PAGE_SIZE, max_results - start),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        feed = feedparser.parse(_get(API_URL, params, attempts=attempts).content)
        if not feed.entries:
            break
        reached_cutoff = False
        for entry in feed.entries:
            paper = _parse_entry(entry)
            if not paper["id"]:
                continue
            if _published_dt(paper) < cutoff:
                reached_cutoff = True
                break
            papers.append(paper)
        if reached_cutoff or len(feed.entries) < params["max_results"]:
            break
        start += config.ARXIV_PAGE_SIZE
    return papers


RSS_URL = "https://rss.arxiv.org/rss/"
RSS_KEEP = {"new", "cross"}   # skip "replace"/"replace-cross": revised versions of older papers


def rss_announcements(categories: list[str], attempts: int = config.ARXIV_ATTEMPTS) -> tuple[str, list[dict]]:
    """Today's arXiv announcement for the given official categories, via the RSS feed (one request).

    Returns (feed date as YYYY-MM-DD or "", papers). Empty on weekends and arXiv holidays.
    """
    feed = feedparser.parse(_get(RSS_URL + "+".join(sorted(set(categories))), {}, attempts=attempts).content)
    day = ""
    if feed.feed.get("published_parsed"):
        day = time.strftime("%Y-%m-%d", feed.feed.published_parsed)
    papers, seen = [], set()
    for entry in feed.entries:
        if entry.get("arxiv_announce_type", "new") not in RSS_KEEP:
            continue
        paper = _parse_entry(entry)
        if not paper["id"] or paper["id"] in seen:
            continue
        seen.add(paper["id"])
        # RSS summaries start with "arXiv:XXXX Announce Type: new Abstract: ..."
        paper["abstract"] = re.sub(r"^arXiv:\S+\s+Announce Type:\s*\S+\s*Abstract:\s*", "", paper["abstract"])
        # RSS gives one comma-separated author string
        if len(paper["authors"]) == 1 and "," in paper["authors"][0]:
            paper["authors"] = [a.strip() for a in paper["authors"][0].split(",") if a.strip()]
        paper["announce_type"] = entry.get("arxiv_announce_type", "new")
        papers.append(paper)
    return day, papers


def search_category(code: str, cutoff: datetime, keywords: str = "",
                    max_results: int = config.MAX_PAPERS, attempts: int = config.ARXIV_ATTEMPTS) -> list[dict]:
    """Newest papers in an official arXiv category (e.g. cs.CL), optionally filtered by keywords."""
    query = f"cat:{code}"
    terms = [t for t in keywords.replace('"', " ").split() if t]
    if terms:
        query += " AND " + " AND ".join(f"all:{t}" for t in terms)
    return search(query, cutoff, max_results=max_results, attempts=attempts)


def fetch_by_id(paper_id: str, attempts: int = config.ARXIV_ATTEMPTS) -> dict | None:
    """Look up one paper's metadata through the id_list API."""
    paper_id = normalize_id(paper_id)
    if not paper_id:
        return None
    feed = feedparser.parse(_get(API_URL, {"id_list": paper_id, "max_results": 1}, attempts=attempts).content)
    for entry in feed.entries:
        paper = _parse_entry(entry)
        if paper["id"] and paper["title"] and paper["title"].lower() != "error":
            return paper
    return None


# --- PDF text -------------------------------------------------------------------
_CONCLUSION_RE = re.compile(
    r"\n\s*(?:[0-9IVX]+\.?\s*)?(conclusions?|concluding remarks|summary and conclusions?|"
    r"discussion and conclusions?)\b[^\n]{0,40}\n", re.I)
_END_RE = re.compile(r"\n\s*(references|bibliography|acknowledge?ments?)\s*\n", re.I)


def download_pdf(pdf_url: str) -> bytes:
    """Download the official preprint PDF from arXiv."""
    return _get(pdf_url, timeout=90, attempts=2).content


def pdf_text(pdf_url: str, max_pages: int = config.PDF_MAX_PAGES) -> str:
    """Download a PDF and extract raw text from the first pages."""
    return text_from_pdf(download_pdf(pdf_url), max_pages)


def text_from_pdf(data: bytes, max_pages: int = config.PDF_MAX_PAGES) -> str:
    """Extract raw text from the first pages of PDF bytes."""
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages[:max_pages]:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # a single broken page should not lose the rest
            continue
    return "\n".join(parts)


def make_excerpt(text: str, max_chars: int) -> str:
    """Keep ~65% from the start plus the Conclusion section, within max_chars."""
    if len(text) <= max_chars:
        return _clean(text)
    head_len = int(max_chars * 0.65)
    head = text[:head_len]
    matches = [m for m in _CONCLUSION_RE.finditer(text) if m.start() > len(text) * 0.3]
    if not matches:
        return _clean(text[:max_chars])
    conclusion = text[matches[-1].start():]
    end = _END_RE.search(conclusion)
    if end:
        conclusion = conclusion[:end.start()]
    conclusion = conclusion[:max_chars - head_len]
    return _clean(head) + "\n\n[...]\n\n" + _clean(conclusion)


def _clean(text: str) -> str:
    text = re.sub(r"-\n(?=[a-z])", "", text)        # re-join hyphenated line breaks
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def pdf_excerpt(pdf_url: str, max_chars: int) -> str:
    """Fail-soft excerpt: returns '' if the PDF cannot be fetched or parsed."""
    try:
        return make_excerpt(pdf_text(pdf_url), max_chars)
    except Exception as exc:
        print(f"  ! PDF text unavailable ({pdf_url}): {exc}")
        return ""
