# Persift — Catch-Up Document

Read this before doing anything. It contains full context for the project.

## What This Is

Persift is an automated internship discovery and resume tailoring pipeline. It polls 5 ATS (Applicant Tracking System) platforms for new software engineering internship postings, filters them by keyword, tailors a resume using GPT-4o, generates a PDF, and sends a Slack notification.

## Architecture Overview

```
main.py                     Entry point — scheduler, seed mode, pipeline orchestration
├── pollers/                 One async poller per ATS platform
│   ├── greenhouse.py        GET API — boards-api.greenhouse.io
│   ├── lever.py             GET API — api.lever.co
│   ├── ashby.py             GET API — api.ashbyhq.com
│   ├── jobvite.py           XML feed — jobs.jobvite.com
│   ├── workday.py           POST JSON API — {slug}.wd{N}.myworkdayjobs.com
│   └── filter.py            Shared keyword filter (role tokens + domain/exclude regex)
├── pipeline/
│   ├── detector.py          Checks SQLite/DynamoDB for already-seen jobs
│   ├── enricher.py          Adds metadata to raw job dicts
│   ├── tailor.py            GPT-4o structured JSON resume tailoring
│   ├── docx_editor.py       Edits base_resume.docx with tailoring data + auto-calibration
│   ├── pdf_gen.py           LibreOffice PDF conversion + ReportLab fallback
│   └── notifier.py          Slack webhook notifications
├── discover_companies.py    Common Crawl CDX company discovery (Greenhouse/Lever/Ashby/Jobvite)
├── config.py                All config: env vars, SEARCH_PROFILE keywords, fallback slug lists
├── db.py                    Database abstraction (SQLite or DynamoDB)
└── resume/
    ├── base_resume.docx     The base resume template
    ├── .resume_calibrated   Auto-calibration flag (SHA-256 hash + adjustments)
    └── ats_prompts/         Per-ATS prompt files for resume tailoring
        ├── greenhouse.txt
        ├── lever.txt
        ├── ashby.txt
        ├── jobvite.txt
        └── workday.txt
```

## ATS Platforms — Current State

| Platform | Companies | Company File Format | Source | Status |
|---|---|---|---|---|
| Greenhouse | 1,166 | `["slug1", "slug2"]` | CDX + SimplifyJobs merge | Active |
| Lever | 303 | `["slug1", "slug2"]` | CDX + SimplifyJobs merge | Active |
| Ashby | 2,228 | `["slug1", "slug2"]` | CDX + SimplifyJobs merge | Active |
| Jobvite | 75 | `["slug1", "slug2"]` | CDX fallback slugs | Active |
| Workday | 1,082 | `[{"slug","wd_num","board","base_url","company_name"}]` | SimplifyJobs extraction | Active |
| Workable | — | — | — | **Removed** (aggressive 429 rate limiting) |
| Recruitee | — | — | — | **Removed** (aggressive 429 rate limiting) |

**Total: 4,854 companies across 5 ATS platforms.**

The database has 2,119 seen jobs from the last seed run.

### Workday Details
Workday is the largest platform (961+ companies in SimplifyJobs, Fortune 500). Its API is a POST to:
```
https://{slug}.{wd_num}.myworkdayjobs.com/wday/cxs/{slug}/{board}/jobs
```
Body: `{"appliedFacets":{},"limit":20,"offset":0,"searchText":"intern"}`

The company list was extracted from `simplify_listings.json` with locale prefix stripping (en-US, fr-FR etc. are path prefixes, not board names). Each entry is a dict with slug, wd_num, board, base_url, company_name.

Workday job descriptions require a separate API call per job — currently `description_plain_text` is empty string. This is a known gap to address later.

### Removed Platforms
`pollers/workable.py` and `pollers/recruitee.py` were deleted. Their company JSON files and ATS prompt files still exist on disk but are not loaded by main.py. They were removed because both platforms rate-limit aggressively with 60-second backoffs, making seed runs take hours.

## Company Discovery

`discover_companies.py` queries Common Crawl CDX API for Greenhouse, Lever, Ashby, and Jobvite. Key details:
- Uses `matchType=domain` (not prefix), `pageSize=1` to avoid 504 timeouts
- Lever has special overrides: 180s timeout, 5 retries, 3s page delay, merges with existing file
- CDX is unreliable (frequent 504s) — retry logic handles it
- **Workday is NOT in discover_companies.py** — its list comes from SimplifyJobs

We also merged slugs from `simplify_listings.json` (downloaded locally) into the Greenhouse/Lever/Ashby JSON files. This was a one-time data merge that significantly boosted Lever coverage (116 → 303).

## Keyword Filtering (pollers/filter.py)

`matches_title(title)` returns True if title has a ROLE keyword AND a DOMAIN keyword and NO EXCLUDE keyword.

- **Role matching**: Explicit token set membership using `_ROLE_TOKENS` frozenset. Title is tokenized with `re.findall(r"[a-z0-9\-]+", title.lower())` and checked against the set. This prevents "international" matching "intern".
- **Domain/Exclude matching**: Word-boundary regex (`\b...\b`) to support multi-word phrases like "data science", "site reliability".

Keywords are configured in `config.py` → `SEARCH_PROFILE` dict.

## Resume Tailoring Pipeline

1. **GPT-4o** (`pipeline/tailor.py`) produces structured JSON with: summary rewrites, bullet modifications, skills swaps, skills additions
2. **docx_editor.py** applies changes to `resume/base_resume.docx`:
   - Auto-calibration on first load: measures page count via LibreOffice, reduces margins to 0.75in if needed, then reduces font by 0.5pt if still overflowing. Uses `.resume_calibrated` flag with SHA-256 hash.
   - Bold-preserving skills editing: `_get_skills_text_and_run()` and `_write_skills_text()` only modify non-bold runs, preserving bold category labels.
   - `_swap_skills()` and `_append_skills()` use these helpers.
3. **pdf_gen.py**: LibreOffice headless conversion, ReportLab fallback.

### GPT-4o Prompt Rules
- `SYSTEM_PROMPT` in `tailor.py` includes: skills swaps JSON schema, banned corporate phrases, "technical detail is sacred" rules, 4 acceptable bullet change types only.
- Per-ATS prompt files in `resume/ats_prompts/` are loaded and appended.

## How to Run

```bash
# Discover companies (optional — auto-runs if files are stale)
python discover_companies.py

# Seed — mark all current jobs as seen (run once before live monitoring)
python main.py --seed

# Live monitoring — polls every POLL_INTERVAL_MINUTES (default 10)
python main.py

# Force fresh discovery before starting
python main.py --discover
```

Last seed run: ~6.5 minutes for 4,854 companies, found 1,289 jobs (1,288 from Workday).

## Config (.env)

```
OPENAI_API_KEY=...
SLACK_WEBHOOK_URL=...
POLL_INTERVAL_MINUTES=10
LOG_LEVEL=INFO
DB_BACKEND=sqlite
```

## Dependencies

```
openai, apscheduler, httpx, reportlab, python-dotenv, beautifulsoup4,
aioboto3, boto3, pymupdf, python-docx, aiosqlite
```

LibreOffice must be installed for PDF conversion (headless mode).

## Key Files to Read First

If you need to modify the system, start with these:
1. `main.py` — orchestration, understand the flow
2. `pollers/filter.py` — keyword matching logic
3. `config.py` — all configuration including SEARCH_PROFILE and fallback slugs
4. `pipeline/tailor.py` — GPT-4o prompt and structured output schema
5. `pipeline/docx_editor.py` — resume editing (most complex file)

## Known Gaps / Future Work

- **Workday job descriptions**: Currently empty. Fetching requires a separate GET per job which is too slow for bulk polling. Could be fetched on-demand during tailoring.
- **Workday company list maintenance**: Currently static from SimplifyJobs. No auto-discovery mechanism. Could periodically re-extract from SimplifyJobs or build a CDX-based discovery.
- **FAANG coverage**: Google, Meta, Apple, Amazon, Bloomberg, JPMorgan use proprietary career portals not covered by any ATS poller. Would need custom scrapers.
- **Unmatched ATS platforms from SimplifyJobs**: iCIMS (146 companies), SmartRecruiters (86), Oracle Cloud (1,194 listings), Eightfold.ai (251) — not yet supported.
- **simplify_listings.json** is downloaded locally (14MB, 19,310 listings). It could be periodically refreshed from GitHub.
