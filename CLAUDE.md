# Persift — Claude Code Context

Persift is an autonomous internship job discovery, matching, tailoring, and auto-apply pipeline. It polls multiple ATS platforms and job aggregators, detects new postings, matches them to users, tailors resumes via a 5-layer pipeline, and auto-applies via Chrome extension. Currently running as a single-user personal tool with full multi-user architecture implemented in DB schema and backend code.

---

## Codebase Map

| File / Folder | What it does |
|---|---|
| `main.py` | Orchestrator. Scheduler, company list loading, polling cycles, seed mode, nightly cleanup job |
| `config.py` | All config and constants. Reads from `.env`. Single source of truth |
| `db.py` | DB abstraction — asyncpg connection pool. Public functions: init_db, filter_new_ids, mark_seen_batch, increment_consecutive_failures, reset_consecutive_failures |
| `discover_companies.py` | CLI tool. Monthly CDX crawl to expand ATS slug lists. `--revalidate` flag re-validates existing slugs |
| `api/server.py` | FastAPI user ingestion API. POST /users, GET /health, GET /jobs/{job_id}/resume, GET /jobs/queue, GET /jobs/queue/count, POST /jobs/{job_id}/applied, POST /jobs/{job_id}/failed |
| `pollers/greenhouse.py` | Polls Greenhouse boards API. 2,127 companies. consecutive_failures wired. |
| `pollers/ashby.py` | Polls Ashby posting API. 2,767 companies. consecutive_failures wired. |
| `pollers/lever.py` | Polls Lever postings API. 303 companies. consecutive_failures wired. |
| `pollers/smartrecruiters.py` | Polls SmartRecruiters API. 885 companies. 3-page cap, 6-slug blacklist. consecutive_failures wired. |
| `pollers/workday.py` | Polls Workday tenant APIs. Being phased out — Jobright covers these |
| `pollers/jobright.py` | Polls Jobright aggregator API. 22 intern categories, hourly, ~48K+ jobs. fetch_jd() for lazy JD fetching. |
| `pollers/custom.py` | Config-driven poller for custom company APIs |
| `pollers/filter.py` | Shared filtering: is_intern_role(), is_entry_level(), assign_categories(), matches_title() |
| `pipeline/detector.py` | Dedup against DB. Marks new jobs as seen |
| `pipeline/enricher.py` | Normalizes raw poller output into consistent shape |
| `pipeline/scorer.py` | Layer 1+2: keyword extraction (pure Python) + relevance scoring (sentence-transformers) |
| `pipeline/injector.py` | Layer 3: keyword injection into resume skills section. JSON-backed tech term list |
| `pipeline/rewriter.py` | Layer 4: LLM bullet rewrite via OpenAI GPT-4o. Migrating to Claude API when credits available |
| `pipeline/formatter.py` | Layer 5: ATS formatting check. 5 checks: word count, section headers, single column, no tables, no page numbers |
| `pipeline/tailor_worker.py` | Tailor worker: processes queued user_jobs through Layers 3-5. Pro users first, Semaphore(5). Outputs .txt and .pdf. |
| `pipeline/matcher.py` | Matching engine: pairs new jobs to users via 6 hard filters + scoring. Runs every 6 minutes. Lazy Jobright JD fetch. |
| `pipeline/notifier.py` | Slack Block Kit notification sender. notify_excluded_company() for amber excluded-company alerts. |
| `pipeline/tailor.py` | Old GPT-4o tailoring — DISABLED, superseded by tailor_worker.py |
| `pipeline/docx_editor.py` | Surgical bullet/skills replacement — DISABLED |
| `pipeline/pdf_gen.py` | LibreOffice docx→PDF — DISABLED |
| `migrations/` | SQL migration files. Run in order against Postgres |
| `extension/manifest.json` | Chrome extension manifest V3. Permissions: storage, alarms, tabs, webNavigation, activeTab |
| `extension/background.js` | Event-driven state machine service worker. All state in chrome.storage.local. chrome.alarms loop. |
| `extension/api.js` | Shared backend API module. getUserId, fetchNextJob, markApplied, markFailed, getResumePdf, getQueueCount |
| `extension/content/greenhouse.js` | Greenhouse form filler. Human timing utilities. Resume PDF upload via DataTransfer. |
| `extension/popup/popup.html` | Extension popup HTML. 6 states rendered by popup.js |
| `extension/popup/popup.js` | Popup state renderer. Reads chrome.storage.local, calls getQueueCount, binds controls. |
| `extension/popup/popup.css` | Popup styles. Dark warm theme matching Persift design system. |

---

## Current Pipeline State

```
poll_all() → detect_new_jobs() → enrich() → notify_slack()
                                                    ↓
                                    [every 6 min] run_matching_cycle()
                                    → 6 hard filters → lazy JD fetch (Jobright) → score_resume()
                                    → queued_matches (status='queued') + notify_matches (status='notify_only')
                                    → notify_excluded_company() for notify_only
                                                    ↓
                                    [every 10 min] run_tailor_cycle()
                                    → Layer 3 inject → Layer 4 rewrite → Layer 5 format check
                                    → WeasyPrint PDF → user_jobs (applying)
                                                    ↓
                                    [Chrome extension] poll_alarm every 5 min
                                    → fetchNextJob() → open tab → greenhouse.js fills form
                                    → markApplied() → user_jobs (applied)
                                                    ↓
                                    [3AM daily] run_cleanup_job()
                                    → expire stale applying jobs → delete old dismissed/applied/failed
```

- **Tier 1 pollers** (Greenhouse, Ashby, Lever, SmartRecruiters, Workday, Custom): every 10 min
- **Tier 2** (Jobright): every 60 min
- **Matching engine**: every 6 minutes
- **Tailor worker**: every 10 minutes
- **Cleanup job**: 3:00 AM daily
- **Extension poll**: every 5 minutes (chrome.alarms)
- **DB backend**: Postgres (asyncpg). SQLite and DynamoDB code removed.

---

## Key Config Values (config.py)

| Constant | Value | Notes |
|---|---|---|
| DATABASE_URL | `postgresql://persift:persift@localhost:5432/persift` | Swap host/creds for RDS in prod |
| POLL_INTERVAL_MINUTES | 10 | Tier 1 polling frequency |
| OPENAI_API_KEY | from env | Used in pipeline/rewriter.py |
| OPENAI_MODEL | `gpt-4o` | Migrating to claude-sonnet-4-20250514 when Anthropic credits available |
| ANTHROPIC_API_KEY | from env (not yet set) | For future Claude API swap in rewriter.py |

---

## Postgres Schema

### jobs
Primary key: `(job_id, ats)`. `categories TEXT[]` with GIN index. `sources TEXT[]` for cross-ATS dedup. `posted_at BIGINT` (ms epoch, 0=unknown). `description` is empty for Jobright jobs — fetched lazily at match time via fetch_jd().

### companies
Slug registry. `consecutive_failures INT` — incremented on transient errors, resets on success. `is_active BOOLEAN` — flipped to FALSE automatically when consecutive_failures >= 5.

### users
`tier TEXT` CHECK ('free', 'pro'). `preferences JSONB` — `{"categories": [...], "work_models": [...]}`. `work_auth JSONB` — `{"needs_sponsorship": bool}`. `resume_text TEXT`. `application_settings JSONB` — full schema:
```json
{
  "job_types": ["intern", "newgrad", "fulltime"],
  "locations": ["Remote", "AZ", "New York"],
  "excluded_companies": [{"slug": "amazon", "reason": "referral"}],
  "blacklisted_companies": ["meta", "google"],
  "auto_submit": false
}
```

GIN indexes on `preferences->'categories'` and `preferences->'work_models'`.

### user_jobs
Application state machine:
- `queued` → matched, waiting for tailor worker
- `applying` → resume tailored, waiting for Chrome extension
- `applied` → extension confirmed submission
- `failed` → error during tailoring or submission
- `failed_stale` → stuck in applying for > 1 hour
- `expired` → stuck in applying for > 48 hours
- `needs_review` → flagged for manual review
- `dismissed` → user skipped
- `notify_only` → excluded company — user notified, not auto-applied

`relevance_score SMALLINT DEFAULT 0`. `keyword_match_data JSONB DEFAULT '{}'` — `{"present": [...], "missing": [...]}`. `retry_count SMALLINT DEFAULT 0`. `ats_format_issues JSONB DEFAULT '[]'` — Layer 5 issues list (migration required, SQL below).

FK: `(job_id, job_ats) → jobs(job_id, ats)`. UNIQUE: `(user_id, job_id, job_ats)`.

### poller_state
One row per poller. `cursor JSONB` replaces `persift_jobright_state.json`.

---

## ⚠️ PENDING MIGRATIONS — RUN BEFORE NEXT SESSION

```sql
-- 1. Add new status values to user_jobs CHECK constraint
ALTER TABLE user_jobs DROP CONSTRAINT IF EXISTS user_jobs_status_check;
ALTER TABLE user_jobs ADD CONSTRAINT user_jobs_status_check
  CHECK (status IN (
    'queued', 'applying', 'applied', 'failed', 'failed_stale',
    'expired', 'needs_review', 'dismissed', 'notify_only'
  ));

-- 2. Add ats_format_issues column (Layer 5 output)
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS ats_format_issues JSONB DEFAULT '[]';

-- 3. Add failure_reason column (extension failed submissions)
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS failure_reason TEXT;
```

---

## Matching Engine Design

**Hard filter (6 checks, Python in-memory):**
1. `job.categories` overlaps `user.preferences.categories`
2. `job.work_model` in `user.preferences.work_models` OR `work_model='Unknown'`
3. If `user.work_auth.needs_sponsorship=true`, skip `h1b_sponsored='No'` jobs
4. `job.experience_level` in `application_settings.job_types` (if set — empty passes all)
5. If `job.work_model` is On-Site or Hybrid AND user has `locations` set — `job.location` must contain one of the user's location strings (case-insensitive substring)
6. `job.company_slug` NOT in `application_settings.blacklisted_companies`

**Post-filter routing:**
- `company_slug` in `excluded_companies` → `status='notify_only'` + Slack amber notification
- Otherwise → `status='queued'`

**Scoring gate:**
- score < 50 → skip
- score 50-79 → Layer 3 only
- score 80+ → Layers 3+4+5 (pro users only for L4)

---

## Tailoring Architecture (Layers 1-5)

| Layer | File | Cost | Notes |
|---|---|---|---|
| L1: Keyword diff | scorer.py | $0 | extract_keywords() — pure Python, stopwords + regex |
| L2: Relevance score | scorer.py | $0 | all-MiniLM-L6-v2, cosine similarity 0-100 |
| L3: Keyword injection | injector.py | $0 | JSON-backed _KNOWN_TECH set, skills section detection |
| L4: LLM rewrite | rewriter.py | ~$0.015/call | GPT-4o now, Claude API when credits available |
| L5: ATS format check | formatter.py | $0 | 5 checks, logs issues, never blocks |

**Target quality: 7-8/10.**

**OpenAI → Claude API migration (when Anthropic credits available):**
- `import anthropic` / `client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)`
- `model = "claude-sonnet-4-20250514"`
- Response: `message.content[0].text`

---

## Chrome Extension Architecture

**Philosophy:** Service worker is completely stateless in memory. All state in `chrome.storage.local`. Event-driven via `chrome.alarms` — no procedural loops, no setTimeout.

**State shape:**
```javascript
{
  phase: 'idle' | 'fetching' | 'tab_open' | 'filling' | 'post_submit_wait',
  current_job: null | { job_id, job_ats, apply_url, company_name, title },
  current_tab_id: null | number,
  phase_started_at: null | number,
  paused: false | true,
  auto_submit: false | true,
  needs_sponsorship: false | true
}
```

**Stale detection:** If `phase !== 'idle'` and `phase_started_at` > 10 minutes old on any alarm fire — declare job dead, call markFailed(), reset to idle.

**Sequential loop:** One job at a time. poll_alarm fires → fetch one job → open tab in background → content script initiates handshake → fill form with human timing → on success markApplied() → next_job_alarm after 30-90s random wait → repeat.

**Popup states:** 0=unconfigured, 1=active/filling, 2=paused, 3=idle/running, 4=post-submit wait, 5=action needed (amber card).

**Auto-submit toggle:** false (default) = fills form, leaves tab open for user to review and submit. true = fills and submits automatically.

**Phase 1 scope:** Greenhouse only. Ashby, Lever, Workday in Phase 2.

---

## Design System (Locked May 25, 2026)

**Direction:** Editorial Quiet Confidence. Personality in microcopy and voice, not visuals.

**Colors:**
| Token | Value | Usage |
|---|---|---|
| Background | #1a1816 | All dark surfaces |
| Surface | #221f1c | Cards, metric tiles |
| Footer | #161412 | Secondary surfaces |
| Border | #2d2a26 | All borders |
| Text primary | #faf8f5 | Primary text |
| Text secondary | #d4cfc4 | Secondary text |
| Text muted | #8a857d | Labels, metadata |
| Green | #97C459 | Active, positive, strong match |
| Amber | #EF9F27 / #FAC775 | Action needed, recruiter response |
| Amber bg | #2a1f0e | Amber card background |
| Amber border | #5a4520 | Amber card border |

**Typography:** Serif (wordmark, greeting, headlines) + Sans (all UI). Free: Source Serif 4 + Inter. Upgrade: GT Sectra + Sohne Mono.

**Logo:** Abstract P mark. SVG at `Persift_Logo_SVG.svg`. 3 paths: black bg, white P mark (merged), black negative space circle. Production-ready.

**Microcopy voice:** Specific, verb-first, no corporate language.
- ✅ "Applying to Stripe. Don't touch this tab."
- ✅ "You applied to 8 jobs while you were sleeping."
- ❌ "Currently processing application."
- ❌ "8 applications submitted today."

---

## User Ingestion API

Run with: `uvicorn api.server:app --reload` (port 8000)

`POST /users` — multipart form:
- `email`, `tier` ('free'|'pro'), `resume` (.pdf or .docx)
- `categories` (comma-separated), `work_models` (comma-separated), `needs_sponsorship` (bool)
- `excluded_companies` (JSON string: `[{"slug": "amazon", "reason": "referral"}]`)
- `blacklisted_companies` (comma-separated slugs)

`GET /jobs/queue?user_id={id}&limit=1` — returns applying jobs for extension
`GET /jobs/queue/count?user_id={id}` — returns count of applying jobs
`GET /jobs/{job_id}/resume?job_ats={ats}&user_id={id}` — returns tailored PDF
`POST /jobs/{job_id}/applied` — marks job as applied
`POST /jobs/{job_id}/failed` — marks job as failed with reason

Current user: `him@persift.com` (pro tier), UUID `46e66cfa-e625-4ffc-b8dc-7bf75e21db26`

---

## How to Run

```bash
# Start Postgres (required first)
docker compose up -d

# Normal live run
python main.py

# Skip company file freshness check
python main.py --no-discover

# Seed mode
python main.py --seed --no-discover

# User ingestion API
uvicorn api.server:app --reload

# Chrome extension
# Chrome → Extensions → Developer mode → Load unpacked → select extension/
# Set user_id via popup input before first run
```

---

## Environment Variables (.env)

```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=          # not yet set — for future Claude API swap
SLACK_WEBHOOK_URL=
POLL_INTERVAL_MINUTES=10
LOG_LEVEL=INFO
DATABASE_URL=postgresql://persift:persift@localhost:5432/persift
```

---

## Dependencies

```bash
pip install weasyprint --break-system-packages   # PDF rendering in tailor_worker.py
pip install asyncpg fastapi uvicorn httpx sentence-transformers openai python-docx pdfplumber
```

---

## Known Issues

| Issue | Severity | Notes |
|---|---|---|
| Pending migrations not yet run | HIGH | Run the 3 SQL statements in PENDING MIGRATIONS section before next session |
| Extension not yet tested | High | Load unpacked, test all 6 popup states, smoke test Greenhouse form filler |
| Behavioral simulation basic | Medium | Mouse trajectories and log-normal keystroke timing not fully implemented — Phase 2 |
| Layer 4 essay generation not built | Medium | Extension flags and skips essay questions — Phase 2 |
| OpenAI → Claude API swap pending | Low | Waiting on Anthropic credits — 3-line change in rewriter.py |
| Workday job IDs are URL paths | Low | Re-appear as new if Workday changes URL structure |
| Stale slugs never re-validated on normal run | Low | Use --revalidate flag monthly |
| Old tailor/PDF pipeline disabled | Intentional | superseded by tailor_worker.py |

---

## What Was Last Worked On (May 25, 2026)

- Jobright JD fetching — lazy fetch at match time, Semaphore(5)
- consecutive_failures wiring — all 4 Tier 1 pollers, auto-deactivation at 5 failures
- Layer 5 ATS formatting check — formatter.py, 5 checks, wired into tailor_worker
- Nightly cleanup job — 3AM APScheduler, 4 DELETE/UPDATE statements
- PDF rendering — WeasyPrint, GET /jobs/{job_id}/resume endpoint
- Company exclusions — excluded_companies + blacklisted_companies, notify_only status, amber Slack alerts
- Chrome extension skeleton — full Phase 1 Greenhouse implementation, all 6 popup states
- Design system locked — colors, typography, microcopy voice, dashboard, popup, landing page
- Logo mark finalized — abstract P mark SVG, production-ready

## Next Session

1. **Run pending migrations** (FIRST — before anything else)
2. **Load and test Chrome extension** — all 6 popup states, state machine transitions
3. **Smoke test Greenhouse form filler** — real application, confirm field detection works
4. **Fix any extension issues** found in testing
5. **Begin web dashboard frontend** — profile setup page first (React/Next.js)
6. **OpenAI → Claude API swap** when Anthropic credits available