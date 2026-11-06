"""Keyword ranking, structured LLM insights and weekly overviews (with fallbacks)."""
import json
import re

from llm import LLM

NOT_STATED = "Not stated in the provided text."

SYSTEM_PROMPT = (
    "You are the science correspondent of a quality broadsheet newspaper, reporting on new research papers.\n"
    "Rules:\n"
    "- Use ONLY the text provided by the user. Do not use outside knowledge.\n"
    "- Never invent numbers, datasets, baselines or results. Quote numbers only if they appear in the text.\n"
    f'- If something is not in the text, write exactly "{NOT_STATED}"\n'
    "- Write in a formal, neutral, journalistic register: third person, measured claims, no hype,\n"
    "  no exclamation marks, no emojis, no first person. Prefer 'the authors report' to 'we'.\n"
    "- Keep it readable for a final-year computer science student; explain technical terms briefly.\n"
    "- Reply with a single JSON object and nothing else."
)

INSIGHT_SCHEMA = """Return JSON with exactly these keys:
{
  "tldr": "a one- or two-sentence standfirst, as under a newspaper headline",
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
    return (f"This week the desk selected {len(featured) + len(more)} new preprints in {domain['title']}. "
            f"Leading the section: {titles}.")


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
                '\n\nWrite a 3-4 sentence editor\'s note on the week (max 90 words) in formal newspaper style, '
                'covering the common themes, '
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

    def brief(self, domain: dict, papers: list[dict]) -> dict:
        """Daily brief for one section, in one LLM request: a lede and one-sentence summaries."""
        if not papers or not self.active:
            return fallback_brief(domain, papers)
        try:
            result = _brief_with_llm(self.llm, domain, papers)
            self.failures = 0
            return result
        except Exception as exc:
            self._note_failure(f"{domain['key']} brief", exc)
            return fallback_brief(domain, papers)


# --- arXiv topic queries, evaluated locally (for RSS items) ----------------------------------
_TOKEN_RE = re.compile(r'\(|\)|\bAND\b|\bOR\b|\bANDNOT\b|(?:all|ti|abs):(?:"[^"]+"|\S+?)(?=[\s()]|$)')


def topic_matches(query: str, text: str) -> bool:
    """Evaluate an arXiv-style query (all:"x y" / all:word with AND, OR, ANDNOT, parentheses)
    against text, so RSS papers get the same topic filter as the weekly API search."""
    if not query:
        return True
    tokens = _TOKEN_RE.findall(query)
    text = text.lower()
    pos = 0

    def term(tok: str) -> bool:
        phrase = tok.split(":", 1)[1].strip('"').lower()
        return re.search(r"\b" + re.escape(phrase), text) is not None

    def atom() -> bool:
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            value = expr()
            pos += 1   # ")"
            return value
        return term(tok)

    def conj() -> bool:
        nonlocal pos
        value = atom()
        while pos < len(tokens) and tokens[pos] in ("AND", "ANDNOT"):
            op = tokens[pos]
            pos += 1
            right = atom()
            value = value and (not right if op == "ANDNOT" else right)
        return value

    def expr() -> bool:
        nonlocal pos
        value = conj()
        while pos < len(tokens) and tokens[pos] == "OR":
            pos += 1
            value = conj() or value
        return value

    try:
        return expr()
    except IndexError:   # malformed query: don't filter everything out
        return True


# --- daily brief ----------------------------------------------------------------------------------
BRIEF_WORDS = 40


def fallback_brief(domain: dict, papers: list[dict]) -> dict:
    summaries = {}
    for p in papers:
        sents = _sentences(p["abstract"])
        words = (sents[0] if sents else p["abstract"]).split()
        summaries[p["id"]] = " ".join(words[:BRIEF_WORDS]) + ("…" if len(words) > BRIEF_WORDS else "")
    n = len(papers)
    lede = (f"{n} new preprint{'s' if n != 1 else ''} in {domain['title']} matched the desk's interests today."
            if n else "")
    return {"lede": lede, "summaries": summaries, "source": "abstract"}


def _brief_with_llm(llm: LLM, domain: dict, papers: list[dict]) -> dict:
    listing = "\n\n".join(f"[{p['id']}] {p['title']}\nABSTRACT: {p['abstract'][:1500]}" for p in papers)
    user = (f"Domain focus: {domain['focus']}\n\nToday's new papers:\n\n{listing}\n\n"
            f"For each paper write a one-sentence summary (max {BRIEF_WORDS} words) of what it does and finds, "
            "in formal newspaper style, using only its abstract. Then write a two-sentence lede (max 50 words) "
            "on today's papers as a whole. Return JSON: "
            '{"lede": "...", "summaries": {"<paper id>": "<summary>", ...}}')
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user}]
    data = extract_json(llm.complete(messages, json_mode=True))
    fallback = fallback_brief(domain, papers)["summaries"]
    got = data.get("summaries") if isinstance(data.get("summaries"), dict) else {}
    summaries = {p["id"]: (_as_text(got.get(p["id"])) if got.get(p["id"]) else fallback[p["id"]]) for p in papers}
    return {"lede": _as_text(data.get("lede")) if data.get("lede") else "", "summaries": summaries, "source": "llm"}
