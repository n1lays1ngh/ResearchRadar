# The Rinfo

*Research, in brief.* A daily brief and a weekly review of new preprints from arXiv.

A research agent that works without being asked. Every Sunday it:

1. pulls the past week's arXiv papers from three sections, each named after an official arXiv category (see [Sections](#sections-official-arxiv-categories)),
2. ranks them by keyword relevance,
3. reads the PDFs of the best ones and has an LLM write a grounded, structured insight for each,
4. adds web context with Tavily (code and discussion links, plus "Beyond arXiv" journal results),
5. emails a newspaper-style edition to you and every subscriber, and archives it as HTML + PDF.

Plus a **daily brief**, Monday to Friday: one request to arXiv's RSS feed for the day's announcements,
the same topic filters, one-sentence summaries (one LLM request per section), emailed to daily subscribers.
arXiv announces nothing at weekends, so on **Saturday** daily subscribers get the **Week in Review** instead:
the best papers from that week's briefs, re-ranked, with a fresh lede per section (no arXiv request at all).
Readers choose the weekly edition, the daily brief, or both.

A companion **website** (React + Vite, with a FastAPI backend, both on Vercel) presents every edition as a
broadsheet newspaper: front page, sections, full reports, an archive with PDF downloads, live arXiv
browsing, **subscribe / unsubscribe** confirmed by email, and a chat on every paper grounded in its PDF.

Everything runs on free tiers: **Gemini API** (LLM), **Tavily** (1,000 credits/month), **GitHub Actions** (scheduler) and **Gmail SMTP** (email).

```
config.py          env vars + the 3 digest sections (arXiv categories, topic filters, colours)
arxiv_categories.py  the official arXiv category taxonomy (codes -> names, groups)
arxiv_client.py    arXiv search / id lookup, PDF -> text excerpt
llm.py             OpenAI-compatible client: throttle, retries, fallback provider, --list-models
summarizer.py      keyword ranking, JSON insights, weekly overviews, abstract fallback
tavily_client.py   web enrichment with a per-run budget
email_builder.py   HTML email (tables + inline CSS) and plain-text version
mailer.py          SMTP sending (one message per recipient; confirmation codes)
pdf_export.py      edition HTML -> PDF with headless Chrome
subscribers.py     encrypted subscriber list on the "subscribers" branch (+ admin CLI)
run_digest.py      the weekly pipeline (arXiv API, full-text reports)
run_brief.py       the daily brief (arXiv RSS, one-line summaries)
api/index.py       FastAPI backend (chat, arXiv lookups, subscriptions), a Vercel Python function
web/               React + Vite website (scripts/sync-data.mjs publishes data/editions as static files)
vercel.json        Vercel build, function and routing settings
.github/workflows/weekly-digest.yml   cron + manual + webhook trigger
data/latest.json   written by each run, read by the chat page
data/editions/     every edition as YYYY-MM-DD.json (website), .html (email) and .pdf
data/briefs/       every daily brief as YYYY-MM-DD.json (website) and .html (email)
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
2. Open **https://myaccount.google.com/apppasswords**, create an app password called "Rinfo", and copy the 16-character password.
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

# Daily brief (RSS): dry run, then real
python run_brief.py --dry-run          # open out/brief-latest.html
python run_brief.py

# Website (two terminals; see section 5)
uvicorn api.index:app --reload --port 8000
cd web && npm install && npm run dev
```

| Flag | Effect |
|---|---|
| `--dry-run` | build `out/` and `data/latest.json` but don't send email |
| `--no-llm` | abstract-based summaries only (0 LLM calls) |
| `--no-fulltext` | don't download PDFs |
| `--no-web` | skip Tavily |
| `--days N` | look back N days instead of `DAYS_BACK` (7) |

Outputs: `out/latest.html`, `out/digest-YYYY-MM-DD.html`, `data/latest.json`, and the archived edition
`data/editions/YYYY-MM-DD.html` + `.pdf`. The PDF needs Google Chrome or Chromium; set `CHROME_BIN` if it
isn't found automatically. Without Chrome the run still works, just without a PDF.

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
| `MAIL_TO` | ✅ | comma-separated recipients (you); subscribers are added automatically |
| `SUBSCRIBERS_KEY` | | enables subscriptions; see [Subscriptions](#subscriptions) |

**Variables** tab: `SITE_URL`, for example `https://research-radar-ebon.vercel.app`. When it is set, every report in the email links to its page on the website, and the footer links to the online edition, the PDF and subscribe / unsubscribe.

Two workflows run on their own:

| Workflow | When | What |
|---|---|---|
| `weekly-digest.yml` | Sundays 08:00 IST (`30 2 * * 0`) | the full edition to weekly subscribers |
| `daily-brief.yml` | Monday to Saturday 11:30 IST (`0 6 * * 1-6`) | the brief to daily subscribers, after arXiv's RSS feed refreshes at midnight US Eastern; on Saturday, the Week in Review (`python run_brief.py --review` builds one by hand) |

They share a concurrency group, so if both run at once one waits instead of racing the other to push.
The brief never sends the same day twice (it checks `data/briefs/<date>.json` for `"sent": true`), and
skips arXiv holidays, when the feed is empty. Run either by hand from the **Actions** tab.

The weekly workflow runs every **Sunday at 08:00 IST** (`30 2 * * 0` UTC). You can also start it from the **Actions** tab (*Run workflow*) or by webhook. Each run uploads `out/` as an artifact and commits `data/latest.json` and `data/editions/`, so the app always has the latest edition and papers.

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

## 5. The website (React + FastAPI on Vercel)

| Page | What it shows |
|---|---|
| `/` | Front page of the latest edition: lead story, other leads, the week in brief, every section |
| `/section/cs.CL` | One section with its overview, reports, briefs and journal links |
| `/paper/<arXiv id>` | The full report, links to arXiv and the PDF, and **Ask about this paper** (streaming chat) |
| `/brief`, `/brief/<date>` | The daily brief: numbered one-line summaries per section, recent briefs |
| `/archive`, `/edition/<date>` | Every edition and brief, with **PDF** and email-version downloads |
| `/browse` | Newest preprints in any of the 155 official arXiv categories, with keywords |
| `/subscribe`, `/confirm` | Subscribe / unsubscribe, confirmed by a link sent by email |

The pages read static files: `web/scripts/sync-data.mjs` copies `data/editions/` into the build, so the
newspaper loads instantly from Vercel's CDN. Only chat, browsing, paper lookup and subscriptions call the
API (`api/index.py`, interactive docs at `/api/docs`).

### Run it locally

```bash
pip install -r requirements-dev.txt          # adds uvicorn
uvicorn api.index:app --reload --port 8000   # terminal 1: the API (reads .env)
cd web && npm install && npm run dev         # terminal 2: http://localhost:5173 (proxies /api)
```

### Deploy on Vercel (free Hobby plan)

1. Go to **https://vercel.com/new**, sign in with GitHub and **Import** this repository. Keep the root
   directory as the repo root; `vercel.json` already sets the build (`web/`) and the API function.
2. Before clicking Deploy, open **Environment Variables** and add (no quotes):

   | Name | Value |
   |---|---|
   | `LLM_API_KEY`, `LLM_MODEL` | as in `.env` (plus the `LLM_FALLBACK_*` ones if you use them) |
   | `TAVILY_API_KEY` | optional, for "Also search the web" |
   | `SMTP_USER`, `SMTP_PASS`, `MAIL_FROM` | used to email confirmation links |
   | `SUBSCRIBERS_KEY`, `GH_TOKEN`, `GITHUB_REPO` | see [Subscriptions](#subscriptions) |
   | `SITE_URL` | your Vercel URL, e.g. `https://research-radar-ebon.vercel.app` (add after the first deploy) |

3. **Deploy.** Copy the URL, set it as `SITE_URL` in Vercel (then **Redeploy**) and as the `SITE_URL`
   repository **variable** on GitHub, so the emails link to the site.
4. Every push to `main` redeploys, including the workflow's weekly commit, so a new edition appears on the
   site within a minute or two of being emailed.

The API is a serverless function (60 s limit), so the first chat on a paper takes a few seconds longer while
it downloads the PDF. Old email links (`/?paper=<id>`) still work and redirect to the paper page.

### Subscriptions

Readers pick **the weekly edition, the daily brief, or both**, enter their email and get a **confirmation link** by email; nothing changes until they
click it (double opt-in, so nobody can sign up or remove someone else). The link carries an encrypted token
that expires after 24 hours. The list itself is stored **encrypted** in `subscribers.enc` on a separate
`subscribers` branch: the repo is public, but without the key the file is unreadable, and signups don't
trigger a redeploy. On each run the workflows decrypt it and sends everyone **their own copy** (nobody sees
other addresses; logs show only counts).

Setup (once):

1. `python subscribers.py --new-key` and copy the key. Generate it only once: a new key can't read the
   existing list.
2. GitHub → **Settings → Secrets and variables → Actions**: add the secret `SUBSCRIBERS_KEY`. The workflow
   reads the list with its own built-in token.
3. GitHub → **Settings → Developer settings → Fine-grained tokens → Generate**: *Only select repositories*
   → this repo, *Repository permissions → Contents: Read and write*. This lets the website save the list.
4. Vercel → project **Settings → Environment Variables**: `SUBSCRIBERS_KEY`, `GH_TOKEN` (the token from
   step 3), `GITHUB_REPO` (`OWNER/REPO`), `SMTP_USER`, `SMTP_PASS`, `MAIL_FROM`. Then **Redeploy**.
5. Optional, locally: the same three subscriber values in `.env`. `python subscribers.py --list` shows the
   subscribers and what each gets; `--add EMAIL --lists weekly,daily` and `--remove EMAIL` edit the list.
   Subscribing again with a different choice updates it.

Check that it works by opening `https://<your site>/api/health`: `"subscriptions": true` means every
setting is present.

> Gmail allows about 500 emails a day, which is plenty for a weekly newsletter.

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
`GitHub Actions (cron / webhook) → arXiv API → keyword ranker → PDF excerpt (pypdf) → LLM (structured JSON) → Tavily → HTML email (SMTP) + data/editions/*.json` and `data/editions → React site on Vercel's CDN`, with `FastAPI (Vercel function) → PDF excerpt → LLM` for chat (RAG-style context stuffing).
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
