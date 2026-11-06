"""Central configuration: env vars (via .env) and the research domains."""
import os

from dotenv import load_dotenv

import arxiv_categories

load_dotenv()


def _load_streamlit_secrets() -> None:
    """On Streamlit (Cloud), copy top-level secrets into the environment so env() sees them.

    Streamlit only does this itself once st.secrets has been touched, so do it explicitly.
    Does nothing outside a running Streamlit app (CLI, GitHub Actions).
    """
    try:
        from streamlit import runtime, secrets
        if not runtime.exists():
            return
        for key, value in secrets.to_dict().items():
            if isinstance(value, (str, int, float, bool)) and not (os.getenv(key) or "").strip():
                os.environ[key] = str(value)
    except Exception:   # no secrets file, or Streamlit not installed
        pass


_load_streamlit_secrets()


def env(name: str, default: str = "") -> str:
    """Read an env var, treating empty / whitespace-only values as unset."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def env_int(name: str, default: int) -> int:
    """Read an integer env var, falling back to the default on bad input."""
    try:
        return int(env(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    """Read a float env var, falling back to the default on bad input."""
    try:
        return float(env(name, str(default)))
    except ValueError:
        return default


# --- LLM (any OpenAI-compatible endpoint) -----------------------------------
LLM_BASE_URL = env("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
LLM_API_KEY = env("LLM_API_KEY")
LLM_MODEL = env("LLM_MODEL", "gemini-3.1-flash-lite")

LLM_FALLBACK_BASE_URL = env("LLM_FALLBACK_BASE_URL")
LLM_FALLBACK_API_KEY = env("LLM_FALLBACK_API_KEY")
LLM_FALLBACK_MODEL = env("LLM_FALLBACK_MODEL")

LLM_DELAY_SECONDS = env_float("LLM_DELAY_SECONDS", 6.0)
LLM_MAX_ATTEMPTS = 3              # hard cap: failed requests can count against quotas
LLM_BACKOFF_SECONDS = env_float("LLM_BACKOFF_SECONDS", 10.0)
LLM_TIMEOUT_SECONDS = env_float("LLM_TIMEOUT_SECONDS", 90.0)
LLM_MAX_CALLS_PER_RUN = env_int("LLM_MAX_CALLS_PER_RUN", 20)

# --- Tavily -------------------------------------------------------------------
TAVILY_API_KEY = env("TAVILY_API_KEY")
TAVILY_MAX_CALLS_PER_RUN = env_int("TAVILY_MAX_CALLS_PER_RUN", 25)

# --- Digest -------------------------------------------------------------------
DAYS_BACK = env_int("DAYS_BACK", 7)
FEATURED_PER_DOMAIN = env_int("FEATURED_PER_DOMAIN", 3)
MORE_LINKS_PER_DOMAIN = env_int("MORE_LINKS_PER_DOMAIN", 6)
MAX_PAPERS = 50                   # hard cap on papers fetched per arXiv search, everywhere
MAX_RESULTS_PER_DOMAIN = min(env_int("MAX_RESULTS_PER_DOMAIN", MAX_PAPERS), MAX_PAPERS)
ARXIV_PAGE_SIZE = MAX_PAPERS      # so a search is a single arXiv request
ARXIV_DELAY_SECONDS = 3.0
ARXIV_ATTEMPTS = env_int("ARXIV_ATTEMPTS", 4)            # GitHub runners often get 429s
ARXIV_BACKOFF_SECONDS = env_float("ARXIV_BACKOFF_SECONDS", 20.0)  # 20 s, 40 s, 80 s (or Retry-After)
PDF_MAX_PAGES = 25
DIGEST_CONTEXT_CHARS = env_int("DIGEST_CONTEXT_CHARS", 9000)
CHAT_CONTEXT_CHARS = env_int("CHAT_CONTEXT_CHARS", 14000)
CHAT_APP_URL = env("CHAT_APP_URL")
USER_AGENT = env("USER_AGENT", "ResearchRadar/1.0 (weekly arXiv digest; personal research use)")

# --- Email --------------------------------------------------------------------
SMTP_HOST = env("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = env_int("SMTP_PORT", 465)
SMTP_USER = env("SMTP_USER")
SMTP_PASS = env("SMTP_PASS")
MAIL_FROM = env("MAIL_FROM", SMTP_USER)
MAIL_TO = [a.strip() for a in env("MAIL_TO").split(",") if a.strip()]

# --- Subscribers (encrypted list on its own branch of the GitHub repo) ------------
GH_TOKEN = env("GH_TOKEN")                                  # contents read/write on the repo
GITHUB_REPO = env("GITHUB_REPO", env("GITHUB_REPOSITORY"))  # "owner/name"; set by GitHub Actions
SUBSCRIBERS_KEY = env("SUBSCRIBERS_KEY")                    # python subscribers.py --new-key
SUBSCRIBERS_BRANCH = env("SUBSCRIBERS_BRANCH", "subscribers")
SUBSCRIBERS_PATH = "subscribers.enc"

# --- Paths --------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE_DIR, "out")
DATA_DIR = os.path.join(BASE_DIR, "data")
LATEST_JSON = os.path.join(DATA_DIR, "latest.json")
EDITIONS_DIR = os.path.join(DATA_DIR, "editions")   # one .html (+ .pdf) per issue
CHROME_BIN = env("CHROME_BIN")                      # optional; auto-detected for the PDF export


def app_url(path: str = "", **params: str) -> str:
    """Link into the Streamlit app (e.g. app_url('newsletter')), or '' when CHAT_APP_URL is unset."""
    if not CHAT_APP_URL:
        return ""
    url = CHAT_APP_URL.rstrip("/") + (f"/{path}" if path else "")
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    return url

# --- Domains ------------------------------------------------------------------
# Each digest section is an official arXiv category (https://arxiv.org/category_taxonomy).
#   categories:  official codes to search; the first one names the section
#   topic_query: optional arXiv query that narrows the categories to your research focus
# "key", "title" and "query" are derived from these at the bottom of this file.
DOMAINS = [
    {
        "categories": ["cs.CL"],
        "emoji": "💬",
        "accent": "#4F46E5",
        "tint": "#EEF2FF",
        "topic_query": 'all:"conversational" OR all:"dialogue" OR all:"chatbot" '
                       'OR all:"retrieval-augmented" OR all:"LLM agent" OR all:"tool use"',
        "keywords": ["conversational", "dialogue", "chatbot", "retrieval-augmented", "agent",
                     "tool use", "multi-turn", "large language model", "llm", "memory"],
        "focus": "conversational AI, dialogue systems, LLM agents and retrieval-augmented generation",
        "web_query": "conversational AI LLM agents retrieval-augmented generation",
        "web_domains": ["aclanthology.org", "openreview.net", "huggingface.co", "research.google"],
    },
    {
        "categories": ["cs.LG", "cs.AI", "cs.CV", "cs.CL", "cs.DC"],
        "emoji": "🌱",
        "accent": "#059669",
        "tint": "#ECFDF5",
        "topic_query": 'all:"green AI" OR all:"energy-efficient" OR all:"carbon footprint" '
                       'OR all:"energy consumption"',
        "keywords": ["green ai", "energy", "carbon", "efficient", "lightweight", "quantization",
                     "distillation", "pruning", "edge device", "on-device", "cpu", "low-power",
                     "sustainab"],
        "focus": "energy-efficient and sustainable machine learning: lower compute, carbon and cost",
        "web_query": "energy-efficient green AI carbon footprint machine learning",
        "web_domains": ["nature.com", "mdpi.com", "sciencedirect.com", "dl.acm.org",
                        "ieeexplore.ieee.org"],
    },
    {
        "categories": ["eess.SY", "eess.SP", "cs.LG", "stat.ML", "physics.app-ph", "cond-mat.mtrl-sci"],
        "emoji": "🔋",
        "accent": "#D97706",
        "tint": "#FFFBEB",
        "topic_query": 'all:battery AND (all:"state of charge" OR all:"state of health" '
                       'OR all:"battery management" OR all:"remaining useful life" OR all:"lithium-ion")',
        "keywords": ["state of charge", "state of health", "battery management",
                     "remaining useful life", "lithium-ion", "degradation", "nasa", "estimation",
                     "capacity", "leakage"],
        "focus": "battery management systems: state-of-charge and state-of-health estimation, "
                 "degradation modelling and remaining useful life prediction",
        "web_query": "battery state of health state of charge estimation machine learning",
        "web_domains": ["sciencedirect.com", "ieeexplore.ieee.org", "mdpi.com", "nature.com",
                        "springer.com"],
    },
]


def _finalise(domain: dict) -> dict:
    """Derive key/title/query from the official categories (validated against the taxonomy)."""
    unknown = [c for c in domain["categories"] if c not in arxiv_categories.NAMES]
    if unknown:
        raise ValueError(f"Not official arXiv categories: {unknown}")
    primary = domain["categories"][0]
    cats = " OR ".join(f"cat:{c}" for c in domain["categories"])
    query = f"({cats})" if len(domain["categories"]) > 1 else cats
    if domain.get("topic_query"):
        query += f" AND ({domain['topic_query']})"
    return {**domain, "key": primary, "title": arxiv_categories.label(primary), "query": query}


DOMAINS = [_finalise(d) for d in DOMAINS]
