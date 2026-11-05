"""Keyword ranking, structured LLM insights and weekly overviews (with fallbacks)."""
import json
import re

from llm import LLM

NOT_STATED = "Not stated in the provided text."

SYSTEM_PROMPT = (
    "You are a careful research assistant who summarises academic papers.\n"
    "Rules:\n"
    "- Use ONLY the text provided by the user. Do not use outside knowledge.\n"
    "- Never invent numbers, datasets, baselines or results. Quote numbers only if they appear in the text.\n"
    f'- If something is not in the text, write exactly "{NOT_STATED}"\n'
    "- Write in plain English for a final-year computer science student; briefly explain jargon.\n"
    "- Reply with a single JSON object and nothing else."
)

INSIGHT_SCHEMA = """Return JSON with exactly these keys:
{
  "tldr": "one or two sentences",
  "problem": "what problem the paper tackles",
  "approach": "how they tackle it",
  "key_findings": ["3 to 5 short bullet strings"],
  "limitations": "limitations or open questions",
  "why_it_matters": "why this matters for: %s",
  "tags": ["three", "short", "tags"]
}"""


# --- ranking ---------------------------------------------------------------------
def score(paper: dict, keywords: list[str]) -> int:
    """Title hit = 3 points; abstract hits = 1 point each, capped at 3 per keyword."""
    total = 0
    for kw in keywords:
        pattern = re.compile(r"\b" + re.escape(kw), re.I)   # word-prefix, never bare substring
        if pattern.search(paper["title"]):
            total += 3
        total += min(len(pattern.findall(paper["abstract"])), 3)
    return total


def rank(papers: list[dict], keywords: list[str], exclude: set[str]) -> list[dict]:
    """Sort by score (then recency), skipping ids already used by another domain."""
    seen, ranked = set(exclude), []
    for p in papers:
        if p["id"] in seen:
            continue
        seen.add(p["id"])
        ranked.append({**p, "score": score(p, keywords)})
    return sorted(ranked, key=lambda p: (p["score"], p["published"]), reverse=True)


# --- JSON helpers --------------------------------------------------------------
def extract_json(text: str) -> dict:
    """Parse a JSON object from model output, tolerating code fences and chatter."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    return json.loads(text[start:end + 1])


def _as_text(value) -> str:
    if isinstance(value, list):
        value = " ".join(str(v) for v in value)
    value = " ".join(str(value or "").split())
    return value or NOT_STATED


def _as_list(value, limit: int) -> list[str]:
    if isinstance(value, str):
        value = [v for v in re.split(r"\n+|(?:^|\s)[-•*]\s+", value) if v.strip()]
    if not isinstance(value, list):
        return []
    items = [" ".join(str(v).split()).lstrip("-•* ") for v in value]
    return [i for i in items if i][:limit]


def normalize_insight(data: dict) -> dict:
    """Validate types and fill gaps so the email template can trust the shape."""
    findings = _as_list(data.get("key_findings"), 5) or [NOT_STATED]
    tags = [t.lower().strip("#") for t in _as_list(data.get("tags"), 3)]
    return {
        "tldr": _as_text(data.get("tldr")),
        "problem": _as_text(data.get("problem")),
        "approach": _as_text(data.get("approach")),
        "key_findings": findings,
        "limitations": _as_text(data.get("limitations")),
        "why_it_matters": _as_text(data.get("why_it_matters")),
        "tags": tags,
        "source": "llm",
    }


# --- fallbacks ---------------------------------------------------------------------
def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def fallback_insight(paper: dict, domain: dict) -> dict:
    """Abstract-only summary used when the LLM is unavailable."""
    sents = _sentences(paper["abstract"])
    tags = [kw for kw in domain["keywords"]
            if re.search(r"\b" + re.escape(kw), paper["title"] + " " + paper["abstract"], re.I)][:3]
    return {
        "tldr": sents[0] if sents else NOT_STATED,
        "problem": NOT_STATED,
        "approach": " ".join(sents[1:3]) or NOT_STATED,
        "key_findings": sents[3:6] or [NOT_STATED],
        "limitations": NOT_STATED,
        "why_it_matters": f"Matched the {domain['key']} topic filter: {domain['focus']}.",
        "tags": tags,
        "source": "abstract",
    }


def fallback_overview(domain: dict, featured: list[dict], more: list[dict]) -> str:
    titles = "; ".join(p["title"] for p in featured[:2])
    return (f"{len(featured) + len(more)} new papers in {domain['title']} made the cut this week. "
            f"Highlights include: {titles}.")


# --- LLM-backed summariser -------------------------------------------------------
class Summarizer:
    """Wraps the LLM with a circuit breaker: after repeated failures, stop calling it."""

    MAX_CONSECUTIVE_FAILURES = 2

    def __init__(self, llm: LLM | None):
        self.llm = llm
        self.failures = 0

    @property
    def active(self) -> bool:
        return self.llm is not None and self.failures < self.MAX_CONSECUTIVE_FAILURES

    def _note_failure(self, what: str, exc: Exception):
        self.failures += 1
        print(f"  ! LLM failed for {what}: {exc}. Using the abstract-based fallback.")
        if not self.active and self.llm is not None:
            print("  ! LLM keeps failing; using fallbacks for the rest of this run.")

    def insight(self, paper: dict, domain: dict, excerpt: str) -> dict:
        """Structured JSON insight for one featured paper."""
        if not self.active:
            return fallback_insight(paper, domain)
        body = excerpt or "(Full text unavailable; use the abstract only.)"
        user = (f"Domain focus: {domain['focus']}\n\n"
                f"TITLE: {paper['title']}\nAUTHORS: {', '.join(paper['authors'][:8])}\n\n"
                f"ABSTRACT:\n{paper['abstract']}\n\nFULL-TEXT EXCERPT:\n{body}\n\n"
                + INSIGHT_SCHEMA % domain["focus"])
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
        try:
            result = normalize_insight(extract_json(self.llm.complete(messages, json_mode=True)))
            if not result["tags"]:
                result["tags"] = fallback_insight(paper, domain)["tags"]
            self.failures = 0
            return result
        except Exception as exc:
            self._note_failure(paper["id"], exc)
            return fallback_insight(paper, domain)

    def overview(self, domain: dict, featured: list[dict], more: list[dict]) -> str:
        """3-4 sentence 'overview of the week' for a domain (max 90 words)."""
        if not self.active or not featured:
            return fallback_overview(domain, featured, more)
        lines = [f"- {p['title']}: {p.get('insight', {}).get('tldr', '')}" for p in featured]
        lines += [f"- {p['title']}" for p in more]
        user = (f"Domain focus: {domain['focus']}\n\nThis week's papers:\n" + "\n".join(lines) +
                '\n\nWrite a 3-4 sentence overview of the week (max 90 words) about common themes, '
                'using only the titles and summaries above. Return JSON: {"overview": "..."}')
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
        try:
            text = _as_text(extract_json(self.llm.complete(messages, json_mode=True)).get("overview"))
            words = text.split()
            self.failures = 0
            return " ".join(words[:90]) + ("…" if len(words) > 90 else "")
        except Exception as exc:
            self._note_failure(f"{domain['key']} overview", exc)
            return fallback_overview(domain, featured, more)
