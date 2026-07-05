# Persift — Architecture & Coupling Map

> **Purpose of this file:** the *connections* between parts of the system — the invariants that, if you change one side without the other, break something elsewhere. Read this before any change that touches a status string, an API response shape, a DB column, a config constant, or the extension↔API contract. The `CLAUDE.md` Codebase Map tells you *what* each file is; this file tells you *what depends on what*.

---

## The spine: `user_jobs.status` lifecycle (TARGET ARCH — migrated Jul 1, 2026)

`user_jobs.status` is the single most coupled value in the system. Every legal edge has **exactly one writer** (the redesign's core rule — no more 4 writers stepping on one column). Changing a status literal in one place silently breaks the others. Full lifecycle + rationale: `DESIGN_NOTES.md`.

```
matcher.py         →  'matched'   (pairing created; tailor's work queue)
                      'notified'  (terminal — excluded-company match; notify, never apply)
tailor_worker.py   →  'matched' → 'preparing'   (atomic claim, FOR UPDATE SKIP LOCKED)
                      'preparing' → 'ready'      (artifact on disk)
                      'preparing' → 'abandoned'  (tailor crashed; self-reported + failure_reason)
api/server.py      →  POST /jobs/claim: 'ready' → 'submitting'  (atomic, stamps lease)
                      POST /jobs/{id}/submitted:    'submitting'|'awaiting_review' → 'submitted'
                      POST /jobs/{id}/awaiting_review: 'submitting' → 'awaiting_review'
                      POST /jobs/{id}/released:     'submitting' → 'ready' (retry) | 'abandoned' (cap)
                      POST /jobs/{id}/heartbeat:    'submitting' → 'submitting' (lease renew)
                      reads 'ready' in: /jobs/queue/count; 'ready'|'submitting' in /jobs/{id}/resume
extension          →  drives claim → submitted | awaiting_review | released (NEVER writes abandoned)
main.py cleanup    →  'submitting' → 'abandoned'  (lease expired — SOLE writer of this edge)
                      'abandoned' → 'ready'        (retry under cap)
                      DELETEs terminal rows ('submitted'/'abandoned') older than 90d
```

Three custodial spans: **System** (`matched`,`preparing`,`ready`) → **Client** (`submitting`,`awaiting_review`) → **World** (`submitted`). Axis A (phase) = `status`; axis B (employer outcome) = `application_outcomes`/`current_stage`; axis C (failure cause) = `failure_reason`. Never conflate them.

**Invariants:**
- Claim is atomic (`UPDATE...RETURNING FOR UPDATE SKIP LOCKED`). The old read-then-act `GET /jobs/queue` gap (double-apply) is gone. `/jobs/claim` is a POST, not a GET.
- Only the CLIENT span uses the lease (`lease_expires_at`, 10 min, renewed by `/heartbeat`). Backend failures are synchronous/self-reported (no lease). **Cleanup is the SOLE writer of `submitting → abandoned`;** the extension never self-abandons.
- `extension_detected` may write ONLY `applied_confirmed` (source→type CHECK on `application_outcomes`). A mechanical failure can never write a fake employer outcome (bug #3, structurally impossible).
- `GET /jobs/{id}/resume` 404s unless status is `ready` or `submitting`.
- Adding/renaming a status requires a migration to `user_jobs_status_check` (currently: matched/preparing/ready/submitting/awaiting_review/submitted/abandoned/notified).
- If you rename any status: grep ALL of `api/server.py`, `pipeline/matcher.py`, `pipeline/tailor_worker.py`, `main.py`, `extension/background.js`, `extension/api.js` before committing.

**Ripple grep recipe (run before touching status):**
```bash
grep -rn "'matched'\|'preparing'\|'ready'\|'submitting'\|'awaiting_review'\|'submitted'\|'abandoned'\|'notified'" \
  api/ pipeline/ main.py extension/
```

---

## Contract: Extension ↔ API

`extension/api.js` is the only place the extension talks to the backend. Every endpoint it calls must exist in `api/server.py` with the matching shape.

| Extension call (`api.js`) | API endpoint (`server.py`) | Couples on |
|---|---|---|
| `claimNextJob()` | `POST /jobs/claim` | body `{user_id}` → atomic `ready`→`submitting`+lease; returns `{job:{job_id, job_ats, apply_url, company_name, title, ...}}` or `{job:null}` |
| `getProfile(userId)` | `GET /users/{user_id}` | flattened profile incl. `visa_type`, `needs_sponsorship`, `custom_answers[]`; moved fields read from COLUMNS, aliased to extension keys (`university`→`school`, DATE→"Mon YYYY") |
| `markSubmitted(jobId, jobAts, snapshots)` | `POST /jobs/{id}/submitted` | body `{user_id, job_ats, snapshot_filled?, snapshot_submitted?}` → `submitted` + `applied_confirmed` outcome + `field_corrections` (if snapshots) + `model_predictions`; ONE txn |
| `markAwaitingReview(...)` | `POST /jobs/{id}/awaiting_review` | body `{user_id, job_ats, reason}` → `submitting`→`awaiting_review` |
| `markReleased(...)` | `POST /jobs/{id}/released` | body `{user_id, job_ats, reason, failure_stage}` → `submitting`→`ready`(retry)|`abandoned`(cap) + `application_attempts`; NO outcome |
| `sendHeartbeat(jobId, jobAts)` | `POST /jobs/{id}/heartbeat` | body `{user_id, job_ats}` → renew lease on `submitting` |
| `getResumePdf(jobId, jobAts)` | `GET /jobs/{id}/resume?job_ats=&user_id=` | FileResponse PDF; requires `ready`|`submitting`; falls back to `base_resume.pdf` |
| `getQueueCount()` | `GET /jobs/queue/count?user_id=` | counts `ready` rows |
| `getDocument(userId, docType)` | `GET /users/{id}/documents/{doc_type}` | only `transcript_undergrad`/`transcript_grad` allowed |

**Invariants:**
- `getProfile` field names map 1:1 to `filler_utils.js` `resolveValue()` category keys. Renaming a JSON key in `server.py:get_user_profile` requires the matching change in `filler_utils.js`. (The endpoint aliases columns back to the old JSON key names, so the 3-way contract with filler_utils is UNCHANGED by the field-home migration.)
- `BASE_URL` in `api.js` (currently `localhost:8000`) must point at the deployed API. CORS in `server.py` (currently `["*"]`) must allow the extension origin. These two are a pair — see DEBUG flags below.
- The **fat `/submitted` endpoint** does status + outcome + field_corrections in ONE transaction — never split it (a submit without its corrections, or vice versa, is a data gap).
- **FIXED Jul 4-5 (Chrome-tested, live):** extension review→submit. The content script now stays alive after `needs_review` (reason `awaiting_user_submit`) instead of exiting — it attaches a `click` listener to the submit button and only starts polling `detectSuccess()` once that real click fires (not from the moment the form is parked; an earlier version polled blindly from parking and false-positived on Greenhouse URLs that never contain `/application`). `background.js`'s `awaiting_review` phase retains `current_job` (no longer wiped by `resetToIdle()`). Popup has a manual fallback (`manual_submit_confirm`) for when the tab/content-script is gone.
- **FIXED Jul 5:** `ready`'s sender-tab check (added when `awaiting_review` started retaining `current_job`) was incomplete — a Fable audit pass found `success`/`failed`/`needs_review`/`heartbeat` were still ungated, so a stale tab from a given-up/reassigned job could still act on whatever job is *currently* current (misattributing a real submit to the wrong job, or renewing the wrong job's lease). All four now require `sender.tab.id === current_tab_id` (see `TAB_SCOPED_MESSAGES` in `background.js`). Every content-script message now also carries its own `job_id`/`job_ats` so a rejected stale `success` can still be logged (console) for manual reconciliation instead of vanishing silently.
- **KNOWN GAP:** `snapshot_filled`/`snapshot_submitted` (two-snapshot field-correction capture) is unbuilt — `message.snapshots` is never populated by any content script, so `/submitted` is always called without snapshots today, on both the auto-submit and review paths. Not a regression from the Jul 4 fix; needs its own design pass.

---

## Contract: profile data location — ONE home per fact (migration 016, Jul 1, 2026)

The dual-home bug class is STRUCTURALLY FIXED. The governing rule: a fact is a **COLUMN** if anything but the form-filler reasons about it (matcher/metrics/ML); **JSONB** if only stored and handed back whole. **No field in both.**

- **COLUMNS on `users`** (system reasons about them): `university`, `major`, `gpa`, `graduation_date` (DATE, canonical), `needs_sponsorship`, `visa_type`, `location_city`, `location_state`, `location_preference`, `resume_text`, `tier`, `email`. Read by `matcher._fetch_active_users` and `get_user_profile`.
- **`users.application_settings` (JSONB)** — form-fill carry-along ONLY: first_name, last_name, phone, linkedin_url, github_url, preferred_name, degree, location_country, eeo_*, work_authorized, previous_employers, desired_hourly/salary_* (comp fallback), custom_answers.

**Consumers of the moved fields (all updated Jul 1):**
- `matcher._fetch_active_users` reads the COLUMNS (was JSONB). Dict keys: `needs_sponsorship`, `visa_type`, `university`, `major`, `graduation_date`.
- `get_user_profile` reads columns, **aliases back to the extension's expected JSON keys** (`university`→`school`; `graduation_date` DATE→`to_char('FMMonth YYYY')`→"May 2027"). So the extension/filler contract is unchanged.
- `create_user` writes `needs_sponsorship` to the COLUMN.

**⚠ `update_profile.py` NOT yet migrated** — it still writes `visa_type`/`needs_sponsorship` into JSONB. Re-running it re-introduces the dual-home. Fix before next use (STATE.md). The old `work_auth`/`work_auth_type` JSONB+column are GONE.

---

## Pipeline layers (tailoring) — who calls what

```
matcher.run_matching_cycle()    → writes 'matched' user_jobs + model_predictions
        ↓ (separate APScheduler job, every 10 min)
tailor_worker.run_tailor_cycle()
        ├─ atomic claim 'matched' → 'preparing'  (FOR UPDATE SKIP LOCKED)
        ├─ L3 inject_keywords()       (pipeline/injector.py)  — all tiers, pure Python
        ├─ L4 rewrite_resume()        (pipeline/rewriter.py)  — PRO ONLY, Semaphore(5)
        │       └─ currently returns input unchanged if OPENAI_API_KEY unset
        ├─ L5 check_ats_format()      (pipeline/formatter.py) — non-blocking, logs issues
        ├─ writes PDF via weasyprint  (lazy import in _write_pdf)
        ├─ success:  'preparing' → 'ready'
        └─ failure:  'preparing' → 'abandoned' + failure_reason (self-reported, no outcome)
```

**Invariants:**
- `rewriter.py` is the **L4 Claude swap point** (currently OpenAI/gpt-4o; strategy is `claude-sonnet-4-6`). `config.OPENAI_MODEL` and `config.REWRITER_MODEL_VERSION` are still gpt-4o — stale vs. strategy (documented issue).
- The tailor worker writes the PDF to `outputs/resumes/{user_id}/{job_id}_{ats}_tailored.pdf`. `GET /jobs/{id}/resume` reads that exact path. Path scheme is a coupling: `safe_id = job_id.replace("/", "_")` in BOTH `tailor_worker.py` and `server.py`.
- `preparing` exists solely for crash recovery: distinguishes "never started" (`matched`, safe to re-run) from "started and died" (`preparing`, may have a partial artifact).
- The old docx/PDF tailoring path (`pipeline/tailor.py`/`docx_editor.py`/`pdf_gen.py`) and `main.py`'s commented tailoring block were DELETED (Jul 1). Live tailoring is matcher→tailor_worker ONLY. `main.py process_single_job()` = enrich + Slack (placeholder for the extension handoff).

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
| `extension/background.js` | `closeTab()` commented in `needs_review`, `success`, `failed`/released, `checkStale` | uncomment all |
| `extension/api.js` | `BASE_URL = localhost:8000` | AWS prod URL |
| `api/server.py` | CORS `allow_origins=["*"]` | `chrome-extension://<id>` |

`BASE_URL` (api.js) and CORS (server.py) are a matched pair — both must point at prod together.

---

## Full table inventory (18 tables — see migrations/ 001–018)

`companies`, `jobs`, `users`, `user_jobs`, `poller_state`, `resume_snapshots`, `application_outcomes`, `application_attempts`, `application_events`, `model_predictions`, `gmail_authorizations`, `gmail_signals`, `user_job_interactions`, `aggregate_benchmarks`, `company_merge_candidates`, `discovery_staging`, `field_corrections` (migration 015 — two-snapshot diff, A/B-only PII), plus `manual_review_queue` (created at runtime by `discovery_worker._ensure_manual_review_table`).

**ML/outcome tables** (`application_outcomes`, `application_attempts`, `model_predictions`) are written opportunistically — every insert is wrapped in try/except that logs a WARNING but never blocks the main status update. So a missing/unmigrated ML column degrades data collection silently rather than failing the apply.
