# Persift — Claude Code Context

> **Doc system. Read the right one:**
>
> **Mandatory floor, every session, no exceptions:** read **this file, then `STATE.md`**, before anything else — in that order. `STATE.md` is what's actually true right now; nothing else in this list overrides it. **If `LAUNCH_PLAN.md` (or any other doc) conflicts with `STATE.md` — a checkbox marked incomplete for something `STATE.md`/`decisions/` show is actually done, a stale status — `STATE.md` wins.** This is a real failure mode, not a hypothetical: a session once read `LAUNCH_PLAN.md` first, trusted a stale unchecked box over `STATE.md`'s current truth, and built a wrong narrative ("P1.2 isn't built") on top of it before self-correcting. Don't repeat that — check `STATE.md`/`decisions/` before trusting any plan-doc checkbox as current status.
>
> **Everything below this line is conditional — read only what the actual task needs, in whatever order that implies. There is no fixed sequence for these; it depends on what you're doing this session, not what happened last session:**
> - **This file (CLAUDE.md)** — stable: identity, codebase map, how to operate, how to run. Rarely changes.
> - **`STATE.md`** — volatile: current progress, DB snapshot, pending work, known issues. Kept short on purpose — it holds only what's currently true and what to do next, not history.
> - **`decisions/`** — why things are the way they are: rejected designs, locked-in architecture, incident postmortems. Check here before re-litigating something that looks like it might have been tried before, or before you need the reasoning behind a current design. Index: `decisions/README.md`.
> - **`ARCHITECTURE.md`** — the coupling map: what depends on what. **Read before changing any status string, API shape, DB column, config constant, or the extension↔API contract.**
> - **`FORM_ENGINE_DESIGN.md`** — LOCKED design for the autofill engine (Extraction → Interpretation → Resolution → Fill/Verify → Telemetry → Replay). **Read before touching filler_utils.js, any content/*.js adapter, field classification, or telemetry.** Its §1 standing rules override ad-hoc instincts. §3.6a is the corpus-harvester spec (P1.2) — see `corpus/README.md` and `corpus_analysis/README.md` for what it built and found. §7 has resolution-layer rules and extraction gaps found along the way. Next: P1.3 replay harness.
> - **`LAUNCH_PLAN.md`** (parent dir) — THE single converged plan (v2, Jul 5): audit fixes + form engine + launch in one spine. Tech-week pitch July 27, 2026 is the only hard date. **Its checkboxes can go stale relative to `STATE.md`/`decisions/` — treat it as scope/dates, not a live status tracker.**
> - **`CatchUpDocs/`** (parent dir) — pre-Claude-Code archive (claude.ai chat hand-off docs, April–June 2026). Historical only, not part of the active doc system — don't extend it.
> - **Generated/non-obvious directories get their own `README.md` at the point of confusion** (e.g. `corpus/README.md`) rather than a full explanation living here — this map only points to them.

Persift is the outcome data layer for early-career hiring. Students get autonomous job applications and automatic tracking (free). Career centers get live visibility into student job searches and outcomes without self-reporting (paid — the revenue side). Outcome capture = apply-through exhaust + Gmail signal parsing (interview vs. not).

---

## How to operate in this codebase (read this first)

This codebase has more coupling than its size suggests — a status string, an API field, or a config constant can have consumers three files away. The failure mode to avoid: taking the shortest route to a goal without tracing what else depends on what you're changing.

**Before editing, for any change that touches one of these, trace consumers first and state the ripple in your plan:**
- a `user_jobs.status` string → see ARCHITECTURE.md "spine"; grep all of api/, pipeline/, main.py, extension/
- an API request/response shape → see ARCHITECTURE.md "Extension ↔ API"; check `extension/api.js` callers
- a `users` column or `application_settings` JSONB key → see "profile data location"; check matcher + getProfile + filler_utils
- `jobs.years_of_experience_min/max`, `jobs.raw_ats_metadata`, or `users.years_of_experience` → check all 5 non-Workday pollers (they write these) + `pipeline/matcher.py`'s hard filter #4 (reads them) — see STATE.md for the full design and why a categorical seniority label was rejected in favor of this
- a `config.py` constant → grep for the symbol; it's the single source of truth, so consumers are everywhere
- a scheduler cadence in main.py → check the matching lookback-window coupling

**Use plan mode (Shift+Tab) for any non-trivial change.** Investigate and present the ripple before writing code. For a change with wide reach, read the relevant section of ARCHITECTURE.md rather than guessing.

**Keep the docs honest.** If you discover the code contradicts these docs, fix the doc in the same change. Doc drift is what degrades reasoning over time.

---

## Codebase Map

| File / Folder | What it does |
|---|---|
| `main.py` | Orchestrator + APScheduler. Flags: --seed, --discover, --no-discover, --check. `process_new_jobs`/`run_jobright_cycle` log new jobs (`_log_new_job`) — Slack notification removed Jul 22 (dead pre-extension placeholder that was slowing down the poll's write phase under load, see `decisions/0006-unbounded-batch-chunking.md`). Cleanup job = lease-expiry sweep (target-arch). |
| `config.py` | All config/constants — single source of truth. SEARCH_PROFILE, fallback slugs, model versions. (Still gpt-4o; strategy is Claude — see STATE.md.) |
| `db.py` | asyncpg pool. `init_db`, `filter_new_ids`, `mark_seen_batch`, `find_incomplete_ids`, `repair_jobs_batch`, `repair_metadata_batch`, `get_company_payload_hash`/`set_company_payload_hash`, `log_company_poll`, `consecutive_failures` helpers. **All batch INSERT/UPDATE functions are chunked** (`_BATCH_CHUNK_SIZE = 2000`, shared `_chunks()` helper) — do not add a new batch function without chunking it; see `decisions/0006-unbounded-batch-chunking.md` for why (an unchunked batch call caused a 13+ min hang at real full-poll volume). |
| `discover_companies.py` | CLI: company discovery crawl → JSON + companies table. Greenhouse crawls both `boards.greenhouse.io` and `job-boards.greenhouse.io` (dual-domain, Jul 21); unions the last N Common Crawl monthly indexes via `--months` (default 6), not just the latest — a single month misses companies a crawler didn't happen to revisit that cycle. |
| `discovery_runner.py` | Slim Render entry point: jobright poll + Worker A as pure asyncio loops (no APScheduler). Subset of main.py — keep in sync. |
| `update_profile.py` | Standalone: merges profile fields into application_settings. Safe to re-run. |
| **api/** | |
| `api/server.py` | FastAPI (target-arch contract). /users, /users/{id}, POST /jobs/claim (atomic), /jobs/{id}/{submitted,awaiting_review,released,heartbeat,resume}, /jobs/queue/count, /users/{id}/documents/{type}. CORS allow_origins=["*"] (debug). |
| **pollers/** | |
| `pollers/{greenhouse,ashby,lever,smartrecruiters,workday,custom,jobright}.py` | Per-source pollers. Workday = post-launch v2 (kept, deferred). **`is_intern_role()` title-drop-gate REMOVED from greenhouse/ashby/lever/smartrecruiters/custom** — see `decisions/0002-intern-only-scope-removed.md`. Still called in `workday.py` and `main.py`'s Jobright cycle only, deliberately. All 5 redesigned pollers run `pollers.seniority.extract_years_of_experience()` and populate `years_of_experience_min/max` + `raw_ats_metadata` on every job (see `decisions/0001-seniority-classification-rejected.md`). **Greenhouse/Ashby/Lever/SmartRecruiters also do a payload-hash (or, for Ashby, real ETag) change-detection skip before parsing** — `db.get_company_payload_hash`/`set_company_payload_hash`, migration 024 — and call `log_company_poll` on every attempt (all 4, not just Greenhouse). See `decisions/0006-unbounded-batch-chunking.md`. **SmartRecruiters/Ashby/Lever also capture a normalized `country` field** (`pollers/geography.py`) and merge a metadata-derived category via `pollers/metadata_categories.py`; **Greenhouse also parses its `metadata[]`/`departments[]` arrays** (`pollers/gh_metadata.py`) — see STATE.md Jul 23 entry for the full data-completeness pass and real before/after numbers. |
| `pollers/seniority.py` | One function: `extract_years_of_experience(*texts)` — literal "N years of experience" regex extraction only, zero inference. Read its module docstring before touching; see `decisions/0001-seniority-classification-rejected.md` for why a categorical design was tried and rejected first. |
| `pollers/geography.py` | Country normalization for SmartRecruiters/Lever (already-clean ISO-2 codes) and Ashby (free-text names needing an alias map — built from a full live census, not guessed). `pollers/filter.py`'s regex-based category classifier has no country awareness; this is a separate, `raw_ats_metadata.country` field. |
| `pollers/gh_metadata.py` | Parses Greenhouse's employer-configurable `metadata[]` array into 5 normalized fields (employment_type/workplace_type/experience_level/salary_range/category_metadata) — only field names confirmed to recur across 2+ companies AND whose real values matched the name (429 distinct names exist total, ~380 single-company noise, deliberately excluded). |
| `pollers/metadata_categories.py` | Maps ATS-provided department/function metadata (SmartRecruiters `function.label`, Ashby/Lever `department`, Greenhouse `departments[].name`) to `pollers/filter.py`'s category taxonomy. Built from full live censuses per ATS, merges into (never replaces) regex-derived categories. **SmartRecruiters' `Customer Service`/`Management` labels deliberately excluded** — see `decisions/0007-scope-detection-not-solvable-by-metadata.md`, a real negative result: both labels carry real in-scope AND real out-of-scope jobs with no reliable separator found. |
| `pollers/filter.py` | Shared filtering: `is_intern_role` (only Workday/Jobright use it now), `assign_categories` (title+full-description regex → category taxonomy). **Only 4 of ~23 categories have been hardened against bare-word false positives — the other ~19 have the same live bug, confirmed with fresh examples Jul 22, still unfixed.** See STATE.md "RESUME HERE". `is_entry_level`/`matches_title` deleted (dead code). Category classification for jobs regex can't resolve (LLM fallback) is designed (`decisions/0003-category-classifier-design.md`) but **not yet built** — needs re-sizing against the Jul 23 real numbers first. |
| `scripts/backfill_country.py`, `backfill_sr_function.py`, `backfill_lever_lists.py`, `backfill_gh_metadata.py`, `backfill_gh_departments.py`, `backfill_metadata_categories.py` | One-time backfill scripts (Jul 23) — each re-polls the relevant ATS live and merges newly-captured fields into existing rows via `jsonb \|\|`, since `db.repair_metadata_batch`'s NULL/`{}`-only guard can't add a new key to already-populated metadata. Not part of the regular poll cycle; run once, keep for reference/re-run if a similar gap resurfaces. |
| **pipeline/** | |
| `pipeline/matcher.py` | Matching: 6 hard filters + scoring. Writes 'matched' user_jobs (excluded→'notified') + model_predictions. Reads profile from COLUMNS. _SCORE_THRESHOLD=50. 6-min lookback (coupled to scheduler cadence). **Hard filter #4 repointed Jul 21**: was a dead `job_types` string-list comparison (never populated by any onboarding flow), now compares `users.years_of_experience` (migration 023) against `jobs.years_of_experience_min` (migration 022) — excludes only when BOTH sides have real data; either NULL passes through unfiltered on this axis (matched on category/location/work_model/sponsorship instead). |
| `pipeline/tailor_worker.py` | Atomic-claims matched→preparing, success→ready, failure→abandoned. L3+L4+L5, pro-first, Semaphore(5), weasyprint lazy import. Writes tailored PDF. |
| `pipeline/scorer.py` | L1+L2: keyword extraction + relevance (all-MiniLM-L6-v2). |
| `pipeline/injector.py` | L3: keyword injection. |
| `pipeline/rewriter.py` | L4: LLM bullet rewrite. **Claude swap point** (currently OpenAI). |
| `pipeline/formatter.py` | L5: ATS format check (non-blocking). |
| `pipeline/discovery_worker.py` | Worker A v1.1.0: discovery_staging → ATS fingerprint → companies. _BATCH_SIZE=50. |
| `pipeline/notifier.py` | Slack Block Kit notifications. |
| `pipeline/detector.py`, `enricher.py` | New-job detection + enrichment. Used by main.py polling path. |
| **migrations/** | 001–029. **18 tables total** (+ `field_corrections` migration 015, `corpus_crawl_state` migration 020, `company_poll_log` migration 021; see ARCHITECTURE.md inventory). Migration 022 (`jobs.years_of_experience_min/max` + `raw_ats_metadata`) and 023 (`users.years_of_experience`) — see `decisions/0001-seniority-classification-rejected.md`. Migration 024 (`companies.last_payload_hash`/`last_response_etag`, `company_poll_log`'s `ok_unchanged` outcome) — see `decisions/0006-unbounded-batch-chunking.md`. Migrations 025-027: harness-support tables/fixes (see `test_pipeline/` and STATE.md). Migration 028 (`jobs.is_active`, listing-freshness flag) — see ARCHITECTURE.md's "jobs.is_active" contract section. Migration 029 (`harness_job_state`'s `no_job_available` outcome, harness-only) — see ARCHITECTURE.md's "last_poll_result" contract section; **status unresolved, see STATE.md's "THE OPEN MYSTERY."** |
| **extension/** | |
| `extension/manifest.json` | MV3. filler_utils.js injected before greenhouse.js + ashby.js. Greenhouse's content_scripts entry has `"all_frames": true` (Aug 8 2026) — ~32% of the Greenhouse corpus is a company's own branded career page embedding the real form in an `<iframe src="job-boards.greenhouse.io/embed/job_app?...">`, not on job-boards.greenhouse.io directly; without `all_frames`, that iframe never got a content script at all (confirmed: zero activity, a silent 90s no-op for every such job). See ARCHITECTURE.md's "Branded-domain / iframe injection" contract section. |
| `extension/filler_utils.js` | ~1240-line shared form-filler. See filler_utils section below. |
| `extension/background.js` | Service-worker state machine. DEBUG_MODE=true, closeTab() disabled (debug — see ARCHITECTURE.md). |
| `extension/api.js` | Shared API module. BASE_URL=localhost:8000 (debug). |
| `extension/content/greenhouse.js` | Greenhouse: resume upload + ATS config; delegates filling to filler_utils. |
| `extension/content/ashby.js` | Ashby filler. Not yet on filler_utils; not confirmed e2e. |
| `extension/popup/` | Popup HTML/JS/CSS. |
| `extension/TEST_COMMANDS.md` | **How to run a real end-to-end extension test.** This is always a manual, hands-on-Chrome process the user drives (reload extension, service-worker console commands, watch it fill/submit a real form) — not something to automate or script. Read this before proposing or attempting any extension test; pick an untouched job first (check `applied_at`/`application_outcomes`/`application_attempts` are empty — never risk a double-apply to a real employer). |
| **landing-page/** | Next/Vite React marketing site. Largely independent of backend. |
| **resume/ats_prompts/** | Per-ATS prompt text files (greenhouse, ashby, lever, smartrecruiters, workday, custom). |
| **scripts/** | db_stats.py, seed_companies.py. |

---

## filler_utils.js — architecture

Shared module injected before every ATS content script. All functions global (no ES modules).

- **Data maps:** VISA_ALIASES, VISA_EXPLANATIONS, VISA_WORK_AUTH (F1: now=Yes/longterm=No), DECLINE_SYNONYMS, US_STATES, FIELD_PATTERNS (35+ categories), QUESTION_ALIASES.
- **DOM utils:** getLabelForEl (5 strategies), getLabelForGroup, classifyField, collectFields (7 strategies, now emits the rich Field object below — P1.1, Jul 17).
- **Rich Field extraction (P1.1, `FORM_ENGINE_DESIGN.md` §3.1):** `enrichField(el, groupEls)` adds `placeholder/name/id/autocomplete/ariaLabel/ariaLabelledByText/role/htmlType/inputMode/pattern/maxLength/required/options/section/description/nearbyText/containerHTML` to every field `collectFields()` returns, additive only (`label`/`inputType`/`el`/`groupEls` unchanged, nothing downstream touched). **`name` reads as `""` on Greenhouse** — its React inputs don't set a DOM `name` attribute (confirmed live, not a bug). **`options` reads as `[]` for closed comboboxes** — the option list only populates in the DOM once opened (confirmed live: Country/School/visa fields). **`section` is a best-effort heuristic, verified on exactly one live posting (ACLU/Greenhouse)** — real heading tags don't exist on that form at all; falls back to a wrapper's first text-only child as a title guess. Do NOT hand-tune this further against individual postings — that's the form-by-form-optimization anti-pattern the design doc's standing rule §1 exists to prevent. P1.2 (corpus harvester) + P1.3 (replay harness) are what actually validate/fix these signals, not one-off manual DOM inspection.
- **Fill mechanisms:** fillTextField, fillNativeSelect, fillReactCombobox, fillTypeaheadCombobox, fillRadioGroup, fillCheckboxGroup, fillIntlPhone.
- **Value resolver:** resolveValue(category, profile, context) — its category keys form a 3-way naming contract with getProfile() JSON keys and application_settings JSONB keys (see ARCHITECTURE.md).
- **Main loop:** runFillerLoop (MAX_PASSES=3, shared seenEls), runPass, waitForDomStability (MutationObserver, 500ms quiet window).

---

## Beta launch scope (locked June 26, 2026)

- ATSes: Greenhouse, Ashby, Lever, SmartRecruiters. Workday = post-launch v2.
- Tailoring L1–L4 (L4 awaits Anthropic key). Gmail tracking: OAuth testing mode, 100-user cap.
- Infra target: AWS (RDS + S3 + Cognito + ECS), migrating off Render. Frontend: Next.js 14 + TS + Tailwind.
- Beta target: 100 users. Chrome Web Store submit ~June 30.

---

## Profile fields — one home per fact (migration 016)

**COLUMNS on `users`** (system reasons about them — matcher/metrics/ML): `email`, `tier`, `university`, `major`, `gpa`, `graduation_date` (DATE, canonical), `needs_sponsorship`, `visa_type`, `location_city`, `location_state`, `location_preference`, `resume_text`.

**`application_settings` JSONB** (form-fill carry-along, never queried): first_name, last_name, phone, linkedin_url, github_url, preferred_name, degree, location_country, eeo_*, work_authorized, previous_employers[], desired_hourly/salary_* (comp fallback), custom_answers[] (until LLM free-text lands).

Governing rule: a fact is a COLUMN if anything but the form-filler reasons about it; JSONB if only stored & handed back whole. **No field in both.** `get_user_profile` aliases columns back to the extension's expected keys (e.g. `university`→`school`, DATE→"Mon YYYY"). Test values live in `update_profile.py`.

---

## Postgres schema (core tables)

- **users:** `id UUID PK`, `tier` ('free'|'pro'), `preferences JSONB`, `resume_text TEXT`, `application_settings JSONB`, + profile COLUMNS: `university/major/gpa/graduation_date/needs_sponsorship/visa_type/location_city/location_state/location_preference` (migration 016). (`work_auth JSONB`/`work_auth_type` removed.)
- **jobs:** composite PK `(job_id, ats)`, `description TEXT DEFAULT ''`, `categories TEXT[]`, `posted_at BIGINT`.
- **user_jobs:** target-arch lifecycle `matched → preparing → ready → submitting → submitted` (+ `awaiting_review`, terminal `abandoned`, terminal `notified`). `lease_expires_at`, `failure_reason`, `submission_mode` (auto|review). **See ARCHITECTURE.md / DESIGN_NOTES.md for full lifecycle + single-writer-per-edge.**
- **field_corrections:** two-snapshot diff (migration 015), A/B-only PII.
- Full 18-table inventory: ARCHITECTURE.md.

---

## How to Run

```powershell
docker compose up -d   # Postgres

# Load .env (PowerShell)
Get-Content .env | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2]) } }

python update_profile.py            # merge profile fields (safe to re-run)
python main.py --no-discover        # full pipeline (descriptions already populate at ingestion, P0.2 — this flag just skips company discovery)
uvicorn api.server:app --reload     # API

python -m pipeline.matcher --all    # run one matcher cycle against ALL jobs (local test)
python main.py --check              # verify import chain on Windows
```

Reset/test snippets (extension service-worker console, psql resets) live in `extension/TEST_COMMANDS.md`.

---

## Environment Variables (.env)

```
OPENAI_API_KEY=        # Layer 4 disabled until set
ANTHROPIC_API_KEY=     # will enable L4 (rewriter.py swap)
SLACK_WEBHOOK_URL=
POLL_INTERVAL_MINUTES=10
LOG_LEVEL=INFO
DATABASE_URL=postgresql://persift:persift@localhost:5432/persift
RENDER_DATABASE_URL=   # external Render Postgres
```
