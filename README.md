# 📡 Research Radar

A research agent that works without being asked. Every Monday it:

1. pulls the past week's arXiv papers from three sections, each named after an official arXiv category (see [Sections](#sections-official-arxiv-categories)),
2. ranks them by keyword relevance,
3. reads the PDFs of the best ones and has an LLM write a grounded, structured insight for each,
4. adds web context with Tavily (code and discussion links, plus "Beyond arXiv" journal results),
5. emails you a styled HTML digest.

A companion **Streamlit app** lets you chat with any paper, grounded in its PDF text.

Everything runs on free tiers: **Gemini API** (LLM), **Tavily** (1,000 credits/month), **GitHub Actions** (scheduler) and **Gmail SMTP** (email).

```
config.py          env vars + the 3 digest sections (arXiv categories, topic filters, colours)
arxiv_categories.py  the official arXiv category taxonomy (codes -> names, groups)
arxiv_client.py    arXiv search / id lookup, PDF -> text excerpt
llm.py             OpenAI-compatible client: throttle, retries, fallback provider, --list-models
summarizer.py      keyword ranking, JSON insights, weekly overviews, abstract fallback
tavily_client.py   web enrichment with a per-run budget
email_builder.py   HTML email (tables + inline CSS) and plain-text version
mailer.py          SMTP sending (SSL on 465, otherwise STARTTLS)
run_digest.py      the weekly pipeline (CLI)
chat_app.py        Streamlit "chat with a paper" app
.github/workflows/weekly-digest.yml   cron + manual + webhook trigger
data/latest.json   written by each run, read by the chat app
```

### Sections (official arXiv categories)

Every section, label and filter uses the [official arXiv category taxonomy](https://arxiv.org/category_taxonomy). Each section is named after its first category. The arXiv query is limited to the listed categories, and a topic filter narrows them to the research focus:

| Section | Categories searched | Topic filter |
|---|---|---|
| 💬 cs.CL · Computation and Language | cs.CL | conversational AI, dialogue, LLM agents, RAG |
| 🌱 cs.LG · Machine Learning | cs.LG, cs.AI, cs.CV, cs.CL, cs.DC | energy-efficient / green ML |
| 🔋 eess.SY · Systems and Control | eess.SY, eess.SP, cs.LG, stat.ML, physics.app-ph, cond-mat.mtrl-sci | battery SoC / SoH / RUL |

To change a section, edit `categories` and `topic_query` in `config.py`. Unknown codes are rejected at startup. Leave `topic_query` empty to include the whole category.
A paper is only used in the first section that picks it, so cross-listed papers never appear twice.

---

## 1. Get your keys

### Gemini API key (LLM)
1. Go to **https://aistudio.google.com**, sign in, then click **Get API key → Create API key**.
2. No credit card is needed. Stay on the **free tier and don't enable billing** on the project. If billing is on, usage beyond the free tier gets charged.
3. Use a key from **its own dedicated Google Cloud project**. Free-tier quota is per project, so a project shared with other apps shares the quota too.
4. Free-tier limits for `gemini-3.1-flash-lite`: **15 requests/min, 500 requests/day, 250K tokens/min**. A weekly run uses about 12 requests (9 paper insights + 3 overviews). Don't switch to a *Pro* model: Pro models are not on the free tier.

### Tavily key (web search, optional)
Sign up at **https://app.tavily.com** and copy the API key. The free plan gives 1,000 credits a month. A weekly run makes at most 25 basic searches (usually 12), which is about 50 credits a month.

### Gmail App Password (email)
1. Turn on **2-Step Verification** for your Google account.
2. Open **https://myaccount.google.com/apppasswords**, create an app password called "Research Radar", and copy the 16-character password.
3. Put it in `SMTP_PASS`. Your normal Gmail password will not work.

---

## 2. Find the exact model ID

Google sometimes publishes models with a suffix (for example `-preview`). To list the IDs your key can use:

```bash
python llm.py --list-models
```

Copy the matching ID (e.g. `gemini-3.1-flash-lite` or `gemini-3.1-flash-lite-preview`) into `LLM_MODEL`. To make one quick test call, run `python llm.py` with no arguments.

---

## 3. Run locally

```bash
python3.11 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                 # then fill in the values

python llm.py --list-models          # check the model ID

# Dry runs first (nothing is emailed; open out/latest.html in a browser)
python run_digest.py --dry-run --no-llm --no-fulltext --no-web   # fastest: arXiv only
python run_digest.py --dry-run                                   # full pipeline, no email

# Real run (sends the email)
python run_digest.py

# Chat app
streamlit run chat_app.py
```

| Flag | Effect |
|---|---|
| `--dry-run` | build `out/` and `data/latest.json` but don't send email |
| `--no-llm` | abstract-based summaries only (0 LLM calls) |
| `--no-fulltext` | don't download PDFs |
| `--no-web` | skip Tavily |
| `--days N` | look back N days instead of `DAYS_BACK` (7) |

Outputs: `out/latest.html`, `out/digest-YYYY-MM-DD.html`, `data/latest.json`.

---

## 4. GitHub Actions (weekly schedule)

Push the repo to GitHub. Then go to **Settings → Secrets and variables → Actions**.

**Secrets** (leave any optional one unset. Empty values fall back to the defaults):

| Secret | Required | Notes |
|---|---|---|
| `LLM_API_KEY` | ✅ | Gemini key |
| `LLM_MODEL` | | defaults to `gemini-3.1-flash-lite` |
| `LLM_BASE_URL` | | defaults to Gemini's OpenAI-compatible endpoint |
| `LLM_FALLBACK_BASE_URL` | | optional second provider |
| `LLM_FALLBACK_API_KEY` | | |
| `LLM_FALLBACK_MODEL` | | |
| `TAVILY_API_KEY` | | without it, web enrichment is skipped |
| `SMTP_HOST` | | defaults to `smtp.gmail.com` |
| `SMTP_PORT` | | defaults to `465` (SSL). Any other port uses STARTTLS |
| `SMTP_USER` | ✅ | your Gmail address |
| `SMTP_PASS` | ✅ | Gmail App Password |
| `MAIL_FROM` | ✅ | usually the same as `SMTP_USER` |
| `MAIL_TO` | ✅ | comma-separated recipients |

**Variables** tab: `CHAT_APP_URL`, for example `https://your-app.streamlit.app`. When it is set, every card gets a "Chat with this paper" button.

The workflow runs every **Monday at 08:00 IST** (`30 2 * * 1` UTC). You can also start it from the **Actions** tab (*Run workflow*) or by webhook. Each run uploads `out/` as an artifact and commits `data/latest.json`, so the chat app always has the latest papers.

### Webhook trigger

Create a fine-grained personal access token that has **Contents: read and write** on this repo (a classic token needs the `repo` scope). Then run:

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer YOUR_GITHUB_TOKEN" \
  https://api.github.com/repos/OWNER/REPO/dispatches \
  -d '{"event_type":"send-digest"}'
```

---

## 5. The chat app

```bash
streamlit run chat_app.py
```
- **Papers from → This week's digest:** filter by the official arXiv categories in your digest (with counts, cross-lists included).
- **Papers from → Latest on arXiv:** pick any of the 155 official categories (type to search). You can add keywords, a look-back window and a maximum number of papers.
- Every paper page shows its category badges and three buttons: **arXiv abstract page**, **Open official PDF** and **Download preprint**. Chat answers come only from that PDF.

### Deploy on Streamlit Community Cloud

1. Go to **https://share.streamlit.io**, then click **Create app** and pick this repo, branch `main`, main file `chat_app.py`.
2. Under **Advanced settings → Secrets**, add top-level keys. Streamlit exposes them as environment variables:
   ```toml
   LLM_API_KEY = "..."
   LLM_MODEL = "gemini-3.1-flash-lite"
   TAVILY_API_KEY = "..."           # optional
   # LLM_FALLBACK_BASE_URL / LLM_FALLBACK_API_KEY / LLM_FALLBACK_MODEL (optional)
   ```
3. Deploy, copy the app URL and save it as the `CHAT_APP_URL` repository variable.
4. Deep links work as `https://your-app.streamlit.app/?paper=2401.01234`. The sidebar also accepts any arXiv id or URL (`arXiv:2401.01234v2`, `https://arxiv.org/abs/...`).

The app redeploys when the workflow commits a new `data/latest.json`, so the paper list stays current.

---

## 6. Optional fallback provider (Groq / Mistral)

If the primary provider still fails after its 3 attempts (429, 5xx or timeout), the same request is retried **once** on the fallback provider. The log prints which provider answered. This applies to the digest and to the chat app, including streaming.

**Groq** (free key at console.groq.com):
```
LLM_FALLBACK_BASE_URL=https://api.groq.com/openai/v1
LLM_FALLBACK_API_KEY=gsk_...
LLM_FALLBACK_MODEL=llama-3.1-8b-instant
```
**Mistral** (free "Experiment" plan at console.mistral.ai):
```
LLM_FALLBACK_BASE_URL=https://api.mistral.ai/v1
LLM_FALLBACK_API_KEY=...
LLM_FALLBACK_MODEL=mistral-small-latest
```

> ⚠️ Groq's free tier has a small **tokens-per-minute** cap. If you use Groq as the *primary* provider, set `LLM_DELAY_SECONDS=25` and `DIGEST_CONTEXT_CHARS=6000`.

You can switch providers with env vars alone. Point `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` at Ollama (`http://localhost:11434/v1`, no key), Groq, Mistral or OpenRouter (`https://openrouter.ai/api/v1`).

---

## 7. Notes for my report

**Architecture.** The system is a batch agent on a schedule plus an interactive companion app, connected by one JSON file.
`GitHub Actions (cron / webhook) → arXiv API → keyword ranker → PDF excerpt (pypdf) → LLM (structured JSON) → Tavily → HTML email (SMTP)` and `data/latest.json → Streamlit chat (RAG-style context stuffing)`.
Each stage is a small module with a narrow interface, and the LLM provider is just an OpenAI-compatible URL plus a model name.

**Grounding.** The LLM sees only the paper's own text: the abstract plus an excerpt made of ~65% from the start and the Conclusion section. The system prompt forbids outside knowledge and invented numbers, and requires *"Not stated in the provided text."* when a field is unknown. In chat, web results come in a separately labelled `WEB RESULTS` block, and the model must tag claims from it with `[web]`. The app lists the source links under the answer.

**Guardrails.**
- Rate limits: 6 s between calls, at most 3 attempts with exponential backoff, a per-run request budget (`LLM_MAX_CALLS_PER_RUN`, default 20) and a circuit breaker that switches to fallbacks after repeated failures. The SDK's own retries are turned off so that hidden retries don't burn daily quota.
- Availability: optional fallback provider, an abstract-based summary if the LLM fails, and a try/except around each paper, so the email still goes out.
- Output validation: JSON mode with a fallback to a plain request, tolerant JSON extraction (code fences), and type normalisation before rendering.
- Safety: every dynamic string is HTML-escaped. Secrets come only from env vars, and empty values count as unset.
- Cost: Tavily is capped at 25 basic searches per run, and the whole system stays on free tiers.

**Evaluation idea.** Build a small gold set: 20–30 papers, each with 3–5 key facts written by a human from the paper. Then measure:
1. *Faithfulness*: the share of generated claims a second LLM judge (or a human) can find in the source excerpt. Also count how many numbers in the insight don't appear in the source text. This check is automatic: regex-extract the numbers and look for each one in the excerpt.
2. *Coverage*: the share of gold facts that appear in the insight.
3. *Ranking quality*: precision@3 of the keyword ranker against human relevance labels.
4. *Ablations*: abstract-only vs. full-text excerpt, and different `DIGEST_CONTEXT_CHARS` values.
