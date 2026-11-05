"""Tavily web enrichment with a global per-run call budget (basic depth only)."""
from urllib.parse import urlparse

import config

CODE_DOMAINS = ["github.com", "huggingface.co", "openreview.net", "reddit.com"]


def host(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.")


def _snippet(text: str, limit: int = 180) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


class WebSearch:
    """Silently disabled when TAVILY_API_KEY is missing or enabled=False."""

    def __init__(self, enabled: bool = True, max_calls: int = config.TAVILY_MAX_CALLS_PER_RUN):
        self.client = None
        self.calls = 0
        self.max_calls = max_calls
        if enabled and config.TAVILY_API_KEY:
            try:
                from tavily import TavilyClient
                self.client = TavilyClient(api_key=config.TAVILY_API_KEY)
            except Exception as exc:
                print(f"  ! Tavily disabled: {exc}")

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def search(self, query: str, max_results: int, **kwargs) -> list[dict]:
        """One basic search -> [{title, url, snippet, host}]; [] on any failure."""
        if not self.enabled or self.calls >= self.max_calls:
            return []
        self.calls += 1
        try:
            resp = self.client.search(query=query[:380], search_depth="basic",
                                      max_results=max_results, **kwargs)
        except Exception as exc:
            print(f"  ! Tavily search failed: {exc}")
            return []
        return [{"title": r.get("title") or host(r.get("url", "")), "url": r.get("url", ""),
                 "snippet": _snippet(r.get("content", "")), "host": host(r.get("url", ""))}
                for r in resp.get("results", []) if r.get("url")]

    def code_links(self, title: str) -> list[dict]:
        """'Code & discussion' links for a featured paper."""
        return self.search(title, 3, include_domains=CODE_DOMAINS)

    def beyond_arxiv(self, domain: dict) -> list[dict]:
        """Recent journal / web results for a domain."""
        return self.search(domain["web_query"], 4, include_domains=domain["web_domains"],
                           time_range="month")
