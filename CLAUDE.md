# Persift — Claude Code Context

Persift is an autonomous internship job discovery and application pipeline. It polls multiple ATS platforms and job aggregators, detects new postings, enriches them, tailors resumes via GPT-4o, and sends Slack notifications. End goal: full auto-apply via Chrome extension. Currently running as a personal-use tool; multi-user architecture designed but not yet implemented.

---

## Codebase Map

| File / Folder | What it does |
|---|---|
| `main.py` | Orchestrator. Scheduler, company list loading, polling cycles, seed mode |
| `config.py` | All config and constants. Reads from `.env`. Single source of truth |
| `db.py` | DB abstraction — SQLite (active) and DynamoDB (inactive). Three public functions: init_db, filter_new_ids, mark_seen_batch |
| `discover_companies.py` | CLI tool. Monthly CDX crawl to expand ATS slug lists. Run: `python discover_companies.py` |
| `pollers/greenhouse.py` | Polls Greenhouse boards API. 2,127 companies |
| `pollers/ashby.py` | Polls Ashby posting API. 2,767 companies |
| `pollers/lever.py` | Polls Lever postings API. 303 companies |
| `pollers/smartrecruiters.py` | Polls SmartRecruiters API. 885 companies. 3-page cap, 6-slug blacklist |
| `pollers/workday.py` | Polls Workday tenant APIs. 1,166 companies. Being phased out — Jobright covers these |
| `pollers/jobright.py` | Polls Jobright aggregator API. 21 intern categories, hourly, ~48K+ jobs |
| `pollers/simplify.py` | Polls SimplifyJobs GitHub listings. Being phased out — hardcoded Summer2026 URL |
| `pollers/custom.py` | Config-driven poller for custom company APIs |
| `pollers/filter.py` | Shared filtering: is_intern_role(), is_entry_level(), assign_categories(), matches_title() |
| `pipeline/detector.py` | Dedup against DB. Marks new jobs as seen |
| `pipeline/enricher.py` | Normalizes raw poller output into consistent shape |
| `pipeline/tailor.py` | GPT-4o resume tailoring. Currently DISABLED in process_single_job() |
| `pipeline/docx_editor.py` | Surgical bullet/skills replacement in base_resume.docx. DISABLED |
| `pipeline/pdf_gen.py` | LibreOffice docx→PDF conversion + ReportLab fallback. DISABLED |
| `pipeline/notifier.py` | Slack Block Kit notification sender |

---

## Current Pipeline State

```
poll_all() → detect_new_jobs() → enrich() → [DISABLED: tailor → docx → pdf] → send_slack_notification()
```

- **Tier 1 pollers** (Greenhouse, Ashby, Lever, SmartRecruiters, Workday, Custom): every 10 min
- **Tier 2** (Jobright, Simplify): every 60 min
- **Tailor / PDF pipeline**: commented out in `process_single_job()` — restore when ready
- **DB backend**: SQLite (`persift.db`). DynamoDB code exists but inactive (`DB_BACKEND=sqlite`)
- **Scheduler**: APScheduler with `max_instances=1` per job

---

## Key Config Values (config.py)

| Constant | Value | Notes |
|---|---|---|
| DB_PATH | `persift.db` | Resolved absolute in db.py via Path(__file__).parent |
| DYNAMODB_TABLE | `persift_seen_jobs` | Inactive |
| POLL_INTERVAL_MINUTES | 10 | Tier 1 polling frequency |
| OPENAI_MODEL | `gpt-4o` | Used in tailor.py |
| OPENAI_MAX_TOKENS | 4096 | Used in tailor.py |
| LIBREOFFICE_TIMEOUT | 60 | Used in pdf_gen.py |
| SIMPLIFY_LISTINGS_URL | GitHub raw URL | Hardcoded to Summer2026 repo — will break at season change |
| WORKDAY_SEARCH_TEXT | `intern` | Pre-filters Workday API server-side |

---

## Data Flow — Single Job (Greenhouse Example)

```
_poll_company() → {job_id, ats, company_slug, title, location, apply_url, description_html, categories}
→ detect_new_jobs() → filter_new_ids() + mark_seen_batch() → new jobs only
→ enrich() → {+ company_name, description_plain_text, experience_level, work_model, h1b_sponsored, posted_at}
→ [DISABLED] tailor_resume() → edit_docx() → convert_docx_to_pdf()
→ send_slack_notification() → Slack
```

---

## SQLite Schema (seen_jobs)

```sql
CREATE TABLE seen_jobs (
    id            TEXT NOT NULL,
    ats           TEXT NOT NULL,
    company_slug  TEXT NOT NULL,
    title         TEXT NOT NULL,
    url           TEXT NOT NULL,
    first_seen_at DATETIME NOT NULL,
    PRIMARY KEY (id, ats)
);
```

Migration to Postgres planned — schema fully designed (see below).

---

## Postgres Schema (Designed, Not Yet Implemented)

Five tables: `jobs`, `companies`, `users`, `user_jobs`, `poller_state`

- `jobs`: canonical job record. `sources TEXT[]` handles cross-source dedup — first hit wins, subsequent sources appended
- `companies`: slug registry with `consecutive_failures` counter, auto-deactivates at 5
- `users`: full profile — tier (free/pro), preferences, resume, work auth, application settings
- `user_jobs`: application state machine — queued → applying → applied/failed/needs_review/dismissed
- `poller_state`: replaces `persift_jobright_state.json` on disk

---

## Known Issues

| Issue | Severity | Notes |
|---|---|---|
| Simplify URL hardcoded to Summer2026 repo | Medium | Will break at season change |
| Workday job IDs are URL paths | Low | Re-appear as new if Workday restructures URLs |
| Stale slugs never re-validated | Low | Existing slugs stay in list even after company closes ATS board. Need --revalidate flag |
| Tailor/PDF pipeline disabled | Intentional | Commented out in process_single_job(). Re-enable when ready |
| DB_BACKEND=sqlite | Intentional | DynamoDB code intact, not used |

---

## How to Run

```bash
# Normal live run
python main.py

# Seed mode — mark all current jobs as seen without notifying (run once before going live)
python main.py --seed

# Force company list refresh via CDX
python main.py --discover

# Run CDX discovery manually (monthly)
python discover_companies.py
```

---

## Environment Variables (.env)

```
OPENAI_API_KEY=
SLACK_WEBHOOK_URL=
POLL_INTERVAL_MINUTES=10
LOG_LEVEL=INFO
DB_BACKEND=sqlite
AWS_REGION=us-east-1
DYNAMODB_TABLE=persift_seen_jobs
DYNAMODB_ENDPOINT=
```

---

## What Was Last Worked On (May 18, 2026)

- Full codebase audit (18 fragile points identified)
- 5 cleanup batches: dead code removal, 6 bug fixes, rename to Persift, config hardening, GitHub push
- Jobvite poller removed (API permanently retired)
- CDX discovery run — 6,082 verified companies across 4 ATS platforms
- CDX fallback loop added — auto-skips crawls still being indexed
- Postgres schema designed (not yet implemented)

## Next Session

1. Postgres migration — provision RDS, create schema, port db.py and pollers
2. Fix stale slug re-validation (--revalidate flag)
3. Decide on Simplify poller — cut or fix URL
4. Multi-user architecture + matching engine design
