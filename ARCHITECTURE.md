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
                      POST /jobs/claim: 'submitting' → 'abandoned'  (claimed row is a dead listing —
                          see jobs.is_active below; loops to claim the next 'ready' row instead of
                          handing the extension a job with no form to find, migration 028)
                      POST /jobs/{id}/submitted:    'submitting'|'awaiting_review' → 'submitted'
                      POST /jobs/{id}/awaiting_review: 'submitting' → 'awaiting_review'
                      POST /jobs/{id}/released:     'submitting' → 'ready' (retry) | 'abandoned' (cap)
                      POST /jobs/{id}/heartbeat:    'submitting' → 'submitting' (lease renew)
                      reads 'ready' in: /jobs/queue/count; 'ready'|'submitting' in /jobs/{id}/resume
extension          →  drives claim → submitted | awaiting_review | released (NEVER writes abandoned)
main.py run_lease_sweep (every 5 min) →
                      'preparing' → 'matched'      (stale >10 min — tailor process died, crash recovery)
                      'submitting' → 'abandoned'   (lease expired — SOLE writer of this edge)
main.py run_cleanup_job (daily 3am) →
                      'abandoned' → 'matched'      (retry under cap, failure_reason LIKE 'tailor_error:%' — no valid artifact, must re-tailor)
                      'abandoned' → 'ready'         (retry under cap, all other mechanical reasons — artifact still good)
                      DELETEs terminal rows ('submitted'/'abandoned') older than 90d
```

Three custodial spans: **System** (`matched`,`preparing`,`ready`) → **Client** (`submitting`,`awaiting_review`) → **World** (`submitted`). Axis A (phase) = `status`; axis B (employer outcome) = `application_outcomes`/`current_stage`; axis C (failure cause) = `failure_reason`. Never conflate them.

**Invariants:**
- Claim is atomic (`UPDATE...RETURNING FOR UPDATE SKIP LOCKED`), and — since P0.6 (Jul 16, 2026) — the claim UPDATE and the job/profile detail SELECT share ONE transaction in `claim_job`, so a process death between them rolls back the claim instead of leaving a `submitting` row nobody was told about. The old read-then-act `GET /jobs/queue` gap (double-apply) is gone. `/jobs/claim` is a POST, not a GET.
- Only the CLIENT span uses the lease (`lease_expires_at`, 10 min, renewed by `/heartbeat`). Backend failures are synchronous/self-reported (no lease) — **except** a hard process kill mid-`preparing`, which `run_lease_sweep`'s staleness check now catches (P0.6; previously unreachable — see `DESIGN_NOTES.md` §Mechanism 2 for the original self-report-only design). **`run_lease_sweep` is the SOLE writer of `submitting → abandoned`;** the extension never self-abandons.
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

## Contract: Branded-domain / iframe injection (Aug 8 2026)

Real gap found in the same timeout investigation that led to `jobs.is_active` below. ~32% of the entire Greenhouse corpus (6,605/20,837 jobs, confirmed by DB query) is hosted on a company's own branded career page (e.g. `www.databricks.com/company/careers/...?gh_jid=...`) that embeds the real Greenhouse form via `<iframe src="https://job-boards.greenhouse.io/embed/job_app?...">`, not on `job-boards.greenhouse.io` directly. Chrome's `content_scripts` only inject into the **top-level frame** by default — on a branded page, `content/greenhouse.js` never ran at all before this fix, confirmed via empty debug logs (zero content-script activity, not a stuck fill) across every real timeout job checked.

- **Fix**: `manifest.json`'s Greenhouse `content_scripts` entry sets `"all_frames": true`. The iframe's own URL (`job-boards.greenhouse.io/embed/...`) already matched the existing `matches` patterns and `host_permissions` — no permission changes needed. `location.href` inside the iframe correctly resolves to that embed URL, which is what `content/greenhouse.js` already expects everywhere it reads `location.href`.
- **A standalone `job-boards.greenhouse.io` job is unaffected**: the top-level frame IS the matching frame there, so `all_frames: true` doesn't create a double-injection risk — exactly one frame matches in either case (the iframe on a branded page, or the top level on a standalone page), never both.
- **Second-order fix, same investigation**: `test_pipeline/job_driver.py`'s `_verify_fields` independently re-checks the DOM for landed values via `page.evaluate(...)`, which targets the main frame only by default — this silently misreported every real branded-domain fill as `VERIFICATION_LANDED_EMPTY` until `_pick_verification_frame()` was added (prefers a `job-boards.greenhouse.io`-hosted frame if one exists, else falls back to the main frame). Harness-only; doesn't affect real users, but would have made the 1000-job baseline test's numbers wrong for ~32% of jobs.
- **Not yet extended**: Ashby/Lever/SmartRecruiters branded-domain embedding patterns are unconfirmed — each needs its own investigation, same scope decision as `jobs.is_active` below.

---

## Contract: `jobs.is_active` — listing freshness (migration 028, Aug 7 2026)

A job can go stale (expire/get pulled on the real ATS site) any time between being harvested and a real user's extension actually claiming it — `matcher.py` only checks a job once (`matcher_checked_at` watermark), and a job can sit in `user_jobs.status='ready'` for minutes to hours before claim. Confirmed live: this was the real cause of a ~12-17% `not_a_standard_greenhouse_form` rate in the test harness (STATE.md), and a real user hitting the same stale job sees the identical failure — not an autofill bug, a queueing gap.

- **Writer**: `api/server.py`'s `POST /jobs/claim` — a liveness check (`_is_greenhouse_job_dead`, Greenhouse only for now, gated on `ats == 'greenhouse'`) runs right after a row is atomically claimed, OUTSIDE the claim transaction (it's a network call; never hold `user_jobs`' `FOR UPDATE SKIP LOCKED` row lock across one). Follows the FULL redirect chain (not just the first hop — a legacy `boards.greenhouse.io` job can 301 to its own `job-boards.greenhouse.io` URL first, still `/jobs/`-shaped, before a later hop reveals the real `?error=true`) and judges the final URL. **Gated on the job's real `ats` field, not a `"greenhouse.io"` substring check on the URL** — a branded-domain `apply_url` (e.g. `www.asm.com/open-vacancies/?gh_jid=...`) routinely has no such substring at all, and an earlier URL-sniffing version of this guard silently exempted every branded-domain job from the check (found live, Aug 8 2026, after the branded-domain iframe fix below made those jobs reachable for the first time). If the listing is dead, sets `jobs.is_active = FALSE` and the `user_jobs` row straight to `abandoned` (`failure_reason='job_no_longer_active'`), then loops to claim the next `ready` row — transparent to the extension, no wasted tab-open.
- **A block is not death — real regression found live (Aug 8 2026) during the first full 1000-job Phase 3 run**: the URL-shape check (`"greenhouse.io" not in final_url or "/jobs/" not in final_url` → dead) assumed a LIVE job's final URL always has that shape — true for standard Greenhouse pages and branded pages that redirect through a `job-boards.greenhouse.io` embed, but false BY DESIGN for a domain like `jobs.bayada.com` that hosts the whole flow on its own domain and never redirects through greenhouse.io at all. A Cloudflare 403/429 on such a domain returns its challenge page at the SAME url (no redirect happens), so this check was silently marking every currently-BLOCKED branded-domain job as permanently DEAD — confirmed live: 146/404 "dead" jobs in one 1000-job run were Bayada alone, almost all still-live jobs caught mid-block, not expired. **Fixed**: a 403/429 response is now treated as inconclusive (assume alive), same posture already used for network errors — a block proves we got blocked, not that the listing is gone. The URL-shape check is also now skipped entirely when no redirect happened at all (`final_url == apply_url`), since that shape tells you nothing about a branded domain that never routes through greenhouse.io either way. A one-time repair pass re-verified every `is_active = FALSE` row against the fixed logic: 437/536 were reactivated, 99 confirmed genuinely dead.
- **Reader**: `pipeline/matcher.py`'s `_fetch_recent_jobs` — `WHERE is_active = TRUE` alongside the existing `matcher_checked_at IS NULL` watermark, so a dead job is never re-matched to a different user.
- **Not yet covered**: Ashby (SPA returns 200 OK even for a nonexistent job id — needs real content/DOM inspection, not a status check), Lever, SmartRecruiters. Each needs its own live investigation before extending `_is_greenhouse_job_dead`'s pattern to them, same as the corpus-harvester's per-ATS scope gap (`decisions/0008`).
- `pipeline.matcher`'s CLI-only `--all`/`--window` debug paths (bottom of the file) deliberately bypass this filter — local test tooling, not a real user-facing matching path.

---

## Contract: `runPollCycleForHarness()` / `no_job_available` / `poll_skipped` — harness-only observability fix (migrations 029+030, Aug 8 2026, **RESOLVED**)

Harness-only, does not affect production. `test_pipeline/job_driver.py`'s `_poll_for_terminal` used to infer what happened by watching `chrome.storage.local.phase` on a 1.5s poll interval — but `background.js`'s poll cycle can complete a full `idle → fetching → idle` round-trip (a claim that correctly finds nothing to do, e.g. every `ready` row was just abandoned by the `jobs.is_active` freshness check above) in well under a second, faster than the poll interval, so the harness could miss the transition entirely and burn the full 90s timeout on an outcome that was actually correct and fast.

**A first fix attempt (a durable `last_poll_result` storage field, checked via timestamp) never actually worked** — confirmed working in every isolated test but fired ZERO times across 40+ real dead-job catches in real `harness_runner.py --workers 4` runs. Root cause, found after two rounds of design review: a single shared, last-write-wins storage slot can still be overwritten by a LATER poll-cycle invocation (the recurring `poll_alarm`, in particular) before the harness's own polling loop ever reads the value it was waiting for — a durable field doesn't help if something else can clobber it before it's read. Full investigation history: STATE.md's "THE OPEN MYSTERY" section.

**The real fix eliminates the storage-polling race entirely** rather than making it identifiable after the fact:

- `extension/background.js`: the poll-cycle logic is now `_runPollCycleCore(source)`, a single shared implementation guarded by a module-scope re-entrancy flag (`_pollCycleRunning`) so two overlapping invocations (e.g. the harness's direct trigger racing the 5-min `poll_alarm`) can't both act on stale state. Two thin wrappers call it: `runPollCycle()` (alarm-driven, fire-and-forget, unchanged behavior) and `runPollCycleForHarness()` (new — **returns its result object directly** to whoever calls it).
- `test_pipeline/job_driver.py`'s `_trigger_poll` calls `runPollCycleForHarness()` via `sw.evaluate(...)` and returns its direct result. Since `sw.evaluate()` only resolves once the JS function itself returns, there is **no polling window between the write and the read that anything else could interleave into** — the exact call the harness made is the exact result it receives, by construction, not by inference from a timestamp or a storage read. `run_job()` branches on the result immediately: `no_job`/`skipped_*` cases resolve right there (new outcomes `no_job_available` / `poll_skipped`, migrations 029/030); only `job_found` falls through to the existing `_poll_for_terminal` phase-watching loop (unaffected — a real fill has no equivalent fast-round-trip race, since `filling`/`awaiting_review` are held states a form fill genuinely takes time to pass through).
- `last_poll_result` in storage is kept, but now purely for manual production/diagnostic visibility (e.g. inspecting extension state from the popup) — nothing depends on it for correctness anymore.
- `test_pipeline/circuit_breaker.py`: both `no_job_available` and `poll_skipped` classified as `_RESET_OUTCOMES`, not `_STREAK_OUTCOMES` — neither is a sign anything is broken.
- `test_pipeline/db_state.py`: both added to `_TERMINAL_OUTCOMES`.

**Verified live, twice, at real scale**: two separate `--count 100 --workers 4` runs (96 and 97 real attempts) both showed the exact bug signature (`outcome='timeout' AND phase_reached='idle'`) at **zero**, confirmed via direct DB query — down from ~40+ per 100-job run in every attempt before this fix. `no_job_available` fired 49 and 42 times respectively, proportional to the real dead-job rate in each random sample. The 3 genuine `timeout`s that did occur in the second run all showed `phase_reached='filling'` — a separate, already-known issue (real jobs that started filling but didn't finish in 90s), not a regression of this bug.

---

## Contract: profile data location — ONE home per fact (migration 016, Jul 1, 2026)

The dual-home bug class is STRUCTURALLY FIXED. The governing rule: a fact is a **COLUMN** if anything but the form-filler reasons about it (matcher/metrics/ML); **JSONB** if only stored and handed back whole. **No field in both.**

- **COLUMNS on `users`** (system reasons about them): `university`, `major`, `gpa`, `graduation_date` (DATE, canonical), `needs_sponsorship`, `visa_type`, `location_city`, `location_state`, `location_preference`, `resume_text`, `tier`, `email`. Read by `matcher._fetch_active_users` and `get_user_profile`. **`location_preference` has no actual reader anywhere in the codebase (confirmed Aug 5 2026 by grep) — work-model matching (Remote/Hybrid/On Site) really happens via `users.preferences.work_models` (JSONB, not a COLUMN), which `pipeline/matcher.py`'s filter #2 reads with case-sensitive matching against `jobs.work_model`'s real Title-Case values. Don't assume `location_preference` does anything until it's wired to a real consumer.**
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
| matching_cycle | 6 min | `run_matching_cycle` — job selection uses a durable watermark (`jobs.matcher_checked_at IS NULL`, migration 019), **not** a wall-clock lookback tied to this cadence. A job stays eligible across any number of skipped/delayed/crashed cycles until some cycle actually marks it checked (only after its matches are durably written — see matcher.py `_mark_jobs_checked`). Changing this cadence no longer requires any matcher.py change. |
| tailor_cycle | 10 min | `run_tailor_cycle` |
| discovery_cycle | 90 min | `run_discovery_cycle` (Worker A) |
| lease_sweep | 5 min | `run_lease_sweep` (P0.6, Jul 16) — time-sensitive: `preparing`/`submitting` crash recovery |
| cleanup_job | daily 03:00 | `run_cleanup_job` — not time-sensitive: abandoned-row retry, 90-day terminal deletion |

**Coupling REMOVED (migration 019, P0.5):** matcher.py no longer has a wall-clock lookback, so the 6-min cadence above is a pure scheduling knob — free to change without touching matcher.py.

**Note:** `discovery_runner.py` is the slim Render deployment that runs ONLY jobright poll + Worker A as pure asyncio loops (no APScheduler). It duplicates a subset of `main.py`'s scheduling. Two entry points, overlapping responsibility — keep in sync.

**Latent landmine, currently dormant (fable_audit Area 4):** `main.py`'s `run_jobright_cycle` and `discovery_runner.py`'s `run_jobright_cycle` are two different functions that both read/write the SAME `poller_state WHERE poller='jobright'` cursor row. As of Jul 2026 this is safe ONLY because they point at different databases (`main.py` → local Docker Postgres; `discovery_runner.py` → Supabase, per STATE.md). If they are ever pointed at the same `DATABASE_URL`, whichever cycle runs second will see the cursor already advanced by the other and silently skip jobs it never actually processed — `discovery_runner.py` only stages to `discovery_staging`, never to `jobs`, so main.py's Jobright→jobs→matcher path would go silently blind. Not fixed; not urgent while the DBs stay separate — flagging so this isn't mistaken for a live bug or re-discovered as a surprise later.

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
content/greenhouse.js  → resume upload + ATS-specific config
        ↓ delegates ALL field filling to:
filler_utils.js  runFillerLoop(profile, context, atsConfig)

content/ashby.js  → fully hand-rolled, NOT yet on filler_utils (see invariants below)
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
