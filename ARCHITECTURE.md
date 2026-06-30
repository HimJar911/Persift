# Persift — Architecture & Coupling Map

> **Purpose of this file:** the *connections* between parts of the system — the invariants that, if you change one side without the other, break something elsewhere. Read this before any change that touches a status string, an API response shape, a DB column, a config constant, or the extension↔API contract. The `CLAUDE.md` Codebase Map tells you *what* each file is; this file tells you *what depends on what*.

---

## The spine: `user_jobs.status` lifecycle

`user_jobs.status` is the single most coupled value in the system. **Three** components write it and the API read-contract depends on the exact strings. Changing a status literal in one place silently breaks the others.

```
matcher.py            →  'queued'        (or 'notify_only' for excluded companies)
tailor_worker.py      →  'queued' → 'applying'   (after tailoring + PDF written to disk)
                         'queued' → 'failed'     (on tailor exception, retry_count++)
api/server.py         reads ONLY 'applying' in:  GET /jobs/queue, GET /jobs/queue/count,
                                                 GET /jobs/{id}/resume
extension (background.js) drives:  'applying' → 'applied' | 'failed' | 'needs_review'
main.py run_cleanup_job →  'applying' → 'expired'      (48h stuck)
                           'applying' → 'failed_stale'  (1h stuck)
                           DELETEs terminal rows (dismissed/applied/failed) older than 90d
```

**Invariants:**
- The queue endpoint (`/jobs/queue`) returns rows with `status='applying'` ONLY. The tailor worker is what advances `queued`→`applying`. If matching produces `queued` rows but the tailor worker never runs, **the extension's queue is empty** even though matches exist.
- `GET /jobs/{id}/resume` 404s unless status is exactly `'applying'` (server.py:417). A tailored PDF on disk is not enough.
- Status strings `expired` / `failed_stale` are written by cleanup but **may not be in the `user_jobs_status_check` CHECK constraint** — code comment at main.py:362 flags the pending migration. Adding a new status string requires a migration to the CHECK constraint or the UPDATE throws.
- If you rename any status string: grep ALL of `api/server.py`, `pipeline/matcher.py`, `pipeline/tailor_worker.py`, `main.py`, `extension/background.js`, `extension/api.js` before committing.

**Ripple grep recipe (run before touching status):**
```bash
grep -rn "'applying'\|'queued'\|'applied'\|'needs_review'\|'failed'\|'dismissed'" \
  api/ pipeline/ main.py extension/
```

---

## Contract: Extension ↔ API

`extension/api.js` is the only place the extension talks to the backend. Every endpoint it calls must exist in `api/server.py` with the matching shape.

| Extension call (`api.js`) | API endpoint (`server.py`) | Couples on |
|---|---|---|
| `fetchNextJob()` | `GET /jobs/queue?user_id=` | returns `{jobs:[{job_id, job_ats, apply_url, company_name, title, ...}]}`; only `applying` |
| `getProfile(userId)` | `GET /users/{user_id}` | returns flattened profile incl. `visa_type`, `needs_sponsorship`, `custom_answers[]`, `previous_employers[]` |
| `markApplied(jobId, jobAts)` | `POST /jobs/{id}/applied` | body `{user_id, job_ats}` → status `applied` + writes `application_outcomes` + `model_predictions` |
| `markNeedsReview(...)` | `POST /jobs/{id}/needs_review` | body `{user_id, job_ats, reason}` → status `needs_review` |
| `markFailed(...)` | `POST /jobs/{id}/failed` | body `{user_id, job_ats, reason, failure_stage}` → status `failed` + `application_attempts` + `application_outcomes` |
| `getResumePdf(jobId, jobAts)` | `GET /jobs/{id}/resume?job_ats=&user_id=` | FileResponse PDF; falls back to `base_resume.pdf` if no tailored file |
| `getDocument(userId, docType)` | `GET /users/{id}/documents/{doc_type}` | only `transcript_undergrad`/`transcript_grad` allowed |

**Invariants:**
- `getProfile` field names map 1:1 to `filler_utils.js` `resolveValue()` category keys. Renaming a JSON key in `server.py:get_user_profile` requires the matching change in `filler_utils.js`.
- `BASE_URL` in `api.js` (currently `localhost:8000`) must point at the deployed API. CORS in `server.py` (currently `["*"]`) must allow the extension origin. These two are a pair — see DEBUG flags below.
- The extension fills the profile returned by `getProfile`; the **profile shape is set by the SQL in `server.py:143-186`**, not by the DB schema directly (it reads from `application_settings` JSONB with COALESCE defaults).

---

## Contract: profile data location (JSONB vs columns)

Two competing homes for user attributes — a known source of confusion:

- **`users.application_settings` (JSONB):** written by `api/server.py:create_user` and `update_profile.py`. Source of truth for the extension (visa_type, eeo_*, custom_answers, location_*, gpa, etc.). The `GET /users/{id}` endpoint reads exclusively from here.
- **`users.requires_sponsorship / work_auth_type / university / graduation_date / major` (top-level columns, added in migration 006):** read by `pipeline/matcher.py:_fetch_active_users` and snapshotted into `user_profile_snapshot` for ML.

**Resolved (Jun 30, 2026):** `create_user` only ever populated the JSONB, leaving the top-level columns NULL for API-created users — which silently emptied the ML `user_profile_snapshot`. Fixed by sourcing those attributes from JSONB in `matcher._fetch_active_users` (the single source of truth), not from the legacy columns. The 5 columns (`requires_sponsorship/work_auth_type/university/graduation_date/major`) remain in the table but are no longer read. JSONB mapping: university←`school`, work_auth_type←`visa_type`, requires_sponsorship←`needs_sponsorship`, major/graduation_date direct.

---

## Pipeline layers (tailoring) — who calls what

```
matcher.run_matching_cycle()    → writes 'queued' user_jobs + model_predictions
        ↓ (separate APScheduler job, every 10 min)
tailor_worker.run_tailor_cycle()
        ├─ L3 inject_keywords()       (pipeline/injector.py)  — all tiers, pure Python
        ├─ L4 rewrite_resume()        (pipeline/rewriter.py)  — PRO ONLY, Semaphore(5)
        │       └─ currently returns input unchanged if OPENAI_API_KEY unset
        ├─ L5 check_ats_format()      (pipeline/formatter.py) — non-blocking, logs issues
        ├─ writes PDF via weasyprint  (lazy import in _write_pdf)
        └─ status 'queued' → 'applying'
```

**Invariants:**
- `rewriter.py` is the **L4 Claude swap point** (currently OpenAI/gpt-4o; strategy is `claude-sonnet-4-6`). `config.OPENAI_MODEL` and `config.REWRITER_MODEL_VERSION` are still gpt-4o — stale vs. strategy (documented issue).
- The tailor worker writes the PDF to `outputs/resumes/{user_id}/{job_id}_{ats}_tailored.pdf`. `GET /jobs/{id}/resume` reads that exact path. Path scheme is a coupling: `safe_id = job_id.replace("/", "_")` in BOTH tailor_worker.py:189 and server.py:420.
- `main.py process_single_job()` (the polling path) has its tailoring/PDF code **commented out** (test mode). So the live tailoring path is matcher→tailor_worker ONLY. Restoring polling-path tailoring = uncomment main.py:223-272.

---

## Orchestration (`main.py`) — scheduler cadences

| Job | Cadence | Function |
|---|---|---|
| poll_cycle | `POLL_INTERVAL_MINUTES` (10) | `run_pipeline` — poll all ATS, detect new |
| jobright_cycle | 60 min | `run_jobright_cycle` |
| matching_cycle | 6 min | `run_matching_cycle` — **note: matcher's `_fetch_recent_jobs` looks back exactly 6 min** (`first_seen_at > NOW() - 6 min`). If you change this cadence, change the lookback window in matcher.py:36 to match or jobs slip through unmatched. |
| tailor_cycle | 10 min | `run_tailor_cycle` |
| discovery_cycle | 90 min | `run_discovery_cycle` (Worker A) |
| cleanup_job | daily 03:00 | `run_cleanup_job` |

**Coupling:** matching cadence (6 min) and the matcher's hardcoded `INTERVAL '6 minutes'` lookback (matcher.py:36) are the same number for a reason. They must stay equal.

**Note:** `discovery_runner.py` is the slim Render deployment that runs ONLY jobright poll + Worker A as pure asyncio loops (no APScheduler). It duplicates a subset of `main.py`'s scheduling. Two entry points, overlapping responsibility — keep in sync.

---

## Company discovery → polling loop

```
discover_companies.py / Worker A  → writes companies table (slug, ats, is_active)
        ↓
main.load_company_lists()  → reads companies WHERE is_active=TRUE per ATS
        │                     falls back to {ats}_companies.json if DB returns 0 rows
        ↓
pollers/{ats}.py  → poll those slugs
        ↓
db.increment_consecutive_failures()  → is_active=FALSE after 5 consecutive failures
```

**Invariant:** a company poll failing 5× in a row flips `is_active=FALSE` (db.py:137), removing it from the next `load_company_lists`. Successful poll resets the counter (db.py:152). The JSON files (`*_companies.json`) are only a fallback when the DB is empty.

---

## ATS form filling (extension content scripts)

```
background.js (state machine)
        ↓ opens apply_url in background tab, phase → 'filling'
content/{greenhouse,ashby}.js  → resume upload + ATS-specific config
        ↓ delegates ALL field filling to:
filler_utils.js  runFillerLoop(profile, context, atsConfig)
```

**Invariants:**
- `filler_utils.js` is injected BEFORE each ATS content script (manifest.json order). Its functions are globals — no ES modules.
- `resolveValue()` category keys ↔ `getProfile()` JSON keys ↔ `application_settings` JSONB keys form a 3-way naming contract. A field that fills correctly requires all three aligned.
- Only `greenhouse.js` is refactored to delegate to filler_utils. `ashby.js` not yet; `lever.js` / `smartrecruiters.js` content scripts don't exist (2 of 4 ATSes can't auto-apply yet).

---

## DEBUG flags — production blockers (must flip before any real user)

These are intentionally set for local testing and will break/leak in production. They are a *set* — flipping one without the others creates a broken half-state.

| File | Flag | Prod value |
|---|---|---|
| `extension/background.js` | `DEBUG_MODE = true` (line 6) | `false` |
| `extension/background.js` | `closeTab()` commented in `needs_review`, `success`, `failed`, `checkStale` | uncomment all |
| `extension/api.js` | `BASE_URL = localhost:8000` | AWS prod URL |
| `api/server.py` | CORS `allow_origins=["*"]` | `chrome-extension://<id>` |

`BASE_URL` (api.js) and CORS (server.py) are a matched pair — both must point at prod together.

---

## Full table inventory (17 tables — see migrations/)

`companies`, `jobs`, `users`, `user_jobs`, `poller_state`, `resume_snapshots`, `application_outcomes`, `application_attempts`, `application_events`, `model_predictions`, `gmail_authorizations`, `gmail_signals`, `user_job_interactions`, `aggregate_benchmarks`, `company_merge_candidates`, `discovery_staging`, plus `manual_review_queue` (created at runtime by `discovery_worker._ensure_manual_review_table`).

**ML/outcome tables** (`application_outcomes`, `application_attempts`, `model_predictions`) are written opportunistically — every insert is wrapped in try/except that logs a WARNING but never blocks the main status update. So a missing/unmigrated ML column degrades data collection silently rather than failing the apply.
