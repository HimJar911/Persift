# Persift — Claude Code Context

> **Active launch plan:** See `LAUNCH_PLAN.md` (at C:\Users\himan\Desktop\Persift\LAUNCH_PLAN.md) for the locked day-by-day build plan. Hard launch date: July 15, 2026. Tech week pitch: July 27, 2026. All session work should be checked against that plan first.
> **Catch-up docs:** See `CatchUpDocs/` for session-by-session summaries. Most recent: `CatchUpDoc - June 27.md`.

Persift is the outcome data layer for early-career hiring. Students get autonomous job applications and automatic tracking. Career centers get live visibility into student job searches and outcomes without self-reporting. Revenue comes from institutions (university career centers), not students.

---

## Strategic Identity (updated June 27, 2026)

**Two-sided product:**
- **Students (free):** Finds roles early (before LinkedIn), tailors resume, auto-applies, tracks automatically. Auto-submit unlocks after user manually reviews first 10 applications.
- **Career centers (paid):** Live visibility into what students are actually doing — applications sent, interviews converting, who's stuck — without waiting for self-reported surveys. Recurring institutional budget. Cohort refills every year so no churn.

**Competitor context:**
- Jobright: horizontal, consumer — won't follow into institutional vertical
- Tsenta (YC S26): on-device, can't centrally collect outcome data. Covers Workday via Gmail OTP flow.
- 12Twenty/CareerLink: CRM for career centers, outcome data still self-reported via surveys. ASU just switched to it (June 2026).

**Outcome capture mechanism:** Apply-through exhaust + Gmail signal parsing for interview/rejection signals. Binary: interview or not-interview. Silence past 3-4 weeks = inferred rejection.

---

## Beta Launch Scope (locked June 26, 2026)

- **ATSes:** Greenhouse, Ashby, Lever, SmartRecruiters. Workday = post-launch v2.
- **Tailoring:** L1-L4 all enabled. Anthropic API key incoming. L4 swap point marked in rewriter.py.
- **Gmail tracking:** OAuth testing mode, 100 user cap, gmail.readonly + calendar.readonly.
- **Infrastructure:** AWS (RDS + S3 + Cognito + ECS). Migrate off Render on Day 8 (July 3).
- **Frontend:** Next.js 14 App Router, TypeScript, Tailwind.
- **Chrome Web Store:** Submit June 30. $5 developer fee.
- **Beta target:** 100 users.

---

## Codebase Map

| File / Folder | What it does |
|---|---|
| `main.py` | Orchestrator. --check flag, --no-discover flag. Scheduler, polling, matching, tailoring. |
| `config.py` | All config and constants. Single source of truth. |
| `db.py` | asyncpg connection pool. init_db, filter_new_ids, mark_seen_batch, consecutive_failures helpers. |
| `discover_companies.py` | CLI tool. Monthly CDX crawl. Writes to JSON + companies table. |
| `discovery_runner.py` | Slim Render scheduler. Jobright poller (60 min) + Worker A (90 min). Health server on $PORT. |
| `api/server.py` | FastAPI API. GET /users/{user_id} returns all profile fields incl. visa_type, needs_sponsorship (from application_settings), custom_answers, previous_employers. POST /jobs/{job_id}/needs_review added. Base-resume fallback in GET /jobs/{job_id}/resume. CORSMiddleware allow_origins=["*"]. |
| `pollers/greenhouse.py` | Polls Greenhouse. 2,127 companies. |
| `pollers/ashby.py` | Polls Ashby. 2,767 companies. |
| `pollers/lever.py` | Polls Lever. 303 companies. |
| `pollers/smartrecruiters.py` | Polls SmartRecruiters. 885 companies. 3-page cap. |
| `pollers/jobright.py` | Polls Jobright aggregator. ~48K+ jobs. |
| `pollers/filter.py` | Shared filtering: is_intern_role(), is_entry_level(), assign_categories(), matches_title() |
| `pipeline/scorer.py` | L1+L2: keyword extraction + relevance scoring (all-MiniLM-L6-v2). |
| `pipeline/injector.py` | L3: keyword injection into resume skills section. |
| `pipeline/rewriter.py` | L4: LLM bullet rewrite. Disabled until Anthropic key arrives. 3-line Claude swap point marked (claude-sonnet-4-6). |
| `pipeline/tailor_worker.py` | Tailor worker: queued → applying. Pro users first, Semaphore(5). weasyprint lazy import. |
| `pipeline/matcher.py` | Matching engine. 6 hard filters + scoring. _SCORE_THRESHOLD=50. |
| `pipeline/notifier.py` | Slack Block Kit notification sender. |
| `pipeline/discovery_worker.py` | Worker A v1.1.0. _BATCH_SIZE=50. |
| `migrations/` | SQL migration files. 001-014 complete. |
| `extension/manifest.json` | MV3. host_permissions: localhost:8000, *.greenhouse.io, boards.greenhouse.io, job-boards.greenhouse.io, *.ashbyhq.com. filler_utils.js injected before greenhouse.js and ashby.js. |
| `extension/filler_utils.js` | **NEW (June 27)** Shared form-filling module. ~1150 lines. Injected before all ATS content scripts. See architecture section below. |
| `extension/background.js` | Service worker state machine. DEBUG_MODE=true (SET FALSE BEFORE PRODUCTION). closeTab() commented out (RESTORE BEFORE PRODUCTION). |
| `extension/api.js` | Shared API module. BASE_URL=localhost:8000 (REVERT TO AWS URL BEFORE PRODUCTION). markNeedsReview() added. |
| `extension/content/greenhouse.js` | Greenhouse filler — now ~185 lines. Handles resume upload + ATS config only. All form filling delegated to filler_utils.js. |
| `extension/content/ashby.js` | Ashby filler. Not yet updated to use filler_utils. Not confirmed end-to-end. |
| `extension/popup/` | Popup HTML/JS/CSS. Needs redesign per launch plan. |
| `extension/TEST_COMMANDS.md` | Commands for OfferUp and Verkada test sessions. |
| `insert_job.py` | Test utility — inserts job into user_jobs. |
| `update_profile.py` | Merges profile fields. Sets visa_type=F1, needs_sponsorship=True, adds immigration support custom answer. Safe to re-run. |
| `scripts/db_stats.py` | DB stats script. |

---

## filler_utils.js — Architecture (as of June 27, 2026)

Shared module injected before every ATS content script. All functions are globals (no ES module syntax).

**Section 1 — Data Maps:**
- `VISA_ALIASES` — 19 visa types → display name variants for dropdown matching
- `VISA_EXPLANATIONS` — 19 visa types → free-text explanation for immigration explanation fields
- `VISA_WORK_AUTH` — 19 visa types → `{ now, longterm }`. F1: now=Yes, longterm=No. US_CITIZEN/GREEN_CARD/H1B: both=Yes.
- `DECLINE_SYNONYMS` — decline/prefer not to answer variants for EEO fields
- `US_STATES` — abbreviation → full name map (all 50 + DC)
- `FIELD_PATTERNS` — 35+ categories, each with `patterns[]` and optional `neg[]`. Categories include: first_name, last_name, full_name, email, phone, linkedin, github, preferred_name, location_*, work_authorized, work_authorized_longterm, needs_sponsorship, visa_status, immigration_explanation, eeo_*, school, degree, major, gpa, graduation_date, compensation, internship_*, previously_employed, referral, cover_letter
- `QUESTION_ALIASES` — 15 semantic remappings for label variations (e.g. "how did you learn about" → "where did you hear about")

**Section 2 — DOM Utilities:**
- `getLabelForEl(el)` — 5 strategies: aria-labelledby, aria-label, label[for], wrapping label, DOM walk up 5 levels
- `getLabelForGroup(inputs)` — walks up from radio/checkbox group to find legend/heading
- `classifyField(label, inputType)` — strips asterisks, matches FIELD_PATTERNS, returns "category__inputType" or null
- `collectFields()` — 7 strategies: label[for], radio groups by name, checkbox groups by name, aria-labelledby, wrapping labels, aria-label (scoped to input/textarea/select/combobox only — NOT buttons/icons), fieldsets

**Section 3 — Fill Mechanisms:**
- `fillTextField(container, value)` — native setter for React
- `fillNativeSelect(container, value, synonyms)` — fuzzy option matching
- `fillReactCombobox(container, value, synonyms)` — aria-controls scoped to prevent portal leakage
- `fillTypeaheadCombobox(container, value)` — type-to-search (school field)
- `fillRadioGroup(container, value, synonyms)`
- `fillCheckboxGroup(container, values)`
- `fillIntlPhone(container, countryName, phoneNumber)` — intl-tel-input library

**Section 4 — Value Resolver:**
- `resolveValue(classifiedCategory, profile, context)` — handles all 35+ categories
- Key behaviors: work_authorized uses VISA_WORK_AUTH.now, work_authorized_longterm uses VISA_WORK_AUTH.longterm, needs_sponsorship returns VISA_EXPLANATION for textarea/text, compensation parses JD DOM for salary range first, gpa builds bucket synonyms (3.52 → "3.5", "3.5 - 4.0", "3.5 or above" etc.)

**Section 5 — Main Loop:**
- `runFillerLoop(profile, context, atsConfig)` — MAX_PASSES=3, shared seenEls Set across passes
- `runPass(profile, context, atsConfig, seenEls)` — collectFields → classify → fill. Tier 1 fallback: custom_answers fuzzy match. Tier 2: log no match.
- `waitForDomStability(formEl, hardTimeoutMs)` — MutationObserver scoped to form, 500ms quiet window

---

## Extension Architecture

**Full flow:**
1. poll_alarm fires every 5 min → fetchNextJob() → /jobs/queue?user_id=...
2. Gets job (status='applying') → opens URL in background tab
3. Tab loads → phase → 'filling'
4. Content script sends 'ready' → background.js fetches profile via getProfile() → responds with full context including visa_type
5. filler_utils.js runFillerLoop() fills all fields (3 passes, DOM stability between passes)
6. auto_submit=false → sends needs_review (marks DB status=needs_review), tab stays open
7. auto_submit=true → clicks submit, waits confirmation
8. background.js marks applied/failed, closes tab, waits 0.5-1.5 min, next job

**CRITICAL — job status flow:** queued → applying → applied|failed|needs_review|dismissed
Queue endpoint returns status='applying' only. Tailor worker advances queued → applying.

**DEBUG flags — MUST restore before any real user:**
- extension/background.js: DEBUG_MODE=false, uncomment closeTab() in needs_review handler and checkStale()
- extension/api.js: revert BASE_URL to AWS production URL
- api/server.py: restrict CORS allow_origins from ["*"] to chrome-extension:// origin

---

## Profile Fields (application_settings JSONB)

| Field | Test value |
|---|---|
| first_name | Himanshu |
| last_name | Jarodiya |
| email | himanshujar911@gmail.com |
| phone | REDACTED-PHONE |
| linkedin_url | REDACTED-LINKEDIN |
| github_url | https://github.com/HimJar911 |
| preferred_name | Himanshu |
| location_city | REDACTED |
| location_state | AZ |
| location_country | United States |
| school | Arizona State University |
| degree | Bachelors |
| major | Computer Science |
| gpa | 3.52 |
| graduation_date | May 2027 |
| visa_type | F1 |
| needs_sponsorship | true |
| eeo_gender | Male |
| eeo_race | Asian |
| eeo_hispanic | false |
| eeo_veteran | I am not a protected veteran |
| eeo_disability | No, I do not have a disability and have not had one in the past |
| work_authorized | true |
| desired_hourly_min | 25 |
| desired_hourly_max | 40 |
| previous_employers | ["Johnson & Johnson", "Virtusa Corporation", "The Silicon Partners", "Arizona State University"] |
| custom_answers | 24-entry JSON array (23 original + immigration support → "No") |

**custom_answers keys (24 entries):**
where did you hear about | how did you hear about this job opportunity | why do you want to work here | why are you interested in this role | tell us about yourself | what are your strengths | what is your greatest weakness | describe a challenge you faced | where do you see yourself in 5 years | what field are you looking to complete your internship | what term were you looking to start | how long of an internship are you looking for | will you consent to a background check | were you previously employed | are you available to work full time | are you able to commute | what is your expected date of graduation | what is your expected graduation | do you have experience with | are you currently enrolled | veteran of the armed forces | hourly compensation expectations | compensation expectations | cover letter | immigration support

---

## Current State (June 27, 2026)

```
[discovery_runner.py — LIVE on Render]
poll_jobright() → dedup → INSERT discovery_staging
                                    ↓
            [every 90 min] run_discovery_cycle() — Worker A v1.1.0

[main.py — NOT YET RUN with --no-discover — all job descriptions still empty]

[Chrome extension]
filler_utils.js architecture — NEW, confirmed working
Geotab (job_id=5153686008): FULLY CONFIRMED ✓
OfferUp (job_id=8004171): CONFIRMED ✓ (work_authorized_longterm=No, F1 explanation, compensation from JD range)
SpaceX (job_id=8403219002): SKIPPED — ITAR, F1 ineligible
Verkada (job_id=5099422007): IN PROGRESS — test not completed
```

**DB snapshot (June 27, 2026):** 1 pro user | jobs: ~18K+ | 4 user_jobs | 6,082+ companies

---

## Pending Work (Next Session — June 28)

| Priority | Task | Notes |
|---|---|---|
| 1 | Complete Verkada test | Verify GPA bucketing works, fix any new failures |
| 2 | E10: DEBUG_MODE=false, restore closeTab(), revert BASE_URL | Must do before any real user |
| 3 | E11: Restrict CORS to chrome-extension origin | Must do before beta |
| 4 | B1: Run main.py --no-discover | Populates job descriptions, enables real matching |
| 5 | B3: Verify tailor worker queued→applying | Needed for real matching flow |
| 6 | Test 2-3 more Greenhouse forms | Target: 7 confirmed forms total for Day 2 goal |
| 7 | E4: School fill fallback (aria-controls never populates) | Silent skip on some forms |
| 8 | Ashby content script update to use filler_utils | Day 3 |
| 9 | Lever content script | Day 3-4 |
| 10 | AI fallback for unmatched fields | Needs Anthropic API key (incoming) |

---

## Known Issues (June 27, 2026)

| Issue | Severity | Notes |
|---|---|---|
| DEBUG_MODE=true in background.js | HIGH | Tab stays open forever. Set false before production. |
| closeTab() disabled in background.js | HIGH | Restore before production. |
| BASE_URL on localhost in api.js | HIGH | Revert to AWS URL before real users. |
| CORS allow_origins=["*"] | HIGH | Restrict to chrome-extension:// before beta. |
| All job descriptions empty | HIGH | Fix: run main.py --no-discover. |
| Lever + SmartRecruiters content scripts missing | HIGH | 2 of 4 ATSes can't auto-apply. |
| School fill silently skips if aria-controls never populates | MEDIUM | No fallback. |
| ITAR filter missing in matcher | MEDIUM | US-citizen-only roles should be filtered for F1 users. |
| AI fallback not implemented | MEDIUM | Unmatched fields get skipped — need Anthropic key first. |
| persift.com landing page missing | HIGH | Needed before public launch. |
| Cybersecurity review not done | HIGH | Required before beta users. |

---

## Postgres Schema

### users
`id UUID PK`. `tier TEXT` CHECK ('free', 'pro'). `preferences JSONB`. `work_auth JSONB`. `resume_text TEXT`. `application_settings JSONB`.

### jobs
Composite PK: `(job_id, ats)`. `description TEXT NOT NULL DEFAULT ''`. `categories TEXT[]`. `sources TEXT[]`. `posted_at BIGINT`.

### user_jobs
Status flow: queued → applying → applied|failed|needs_review|dismissed.

---

## How to Run

```powershell
# Start Postgres
docker compose up -d

# Load .env vars (PowerShell)
Get-Content .env | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2]) } }

# Update profile (visa_type, needs_sponsorship, immigration answer) — safe to re-run
python update_profile.py

# Full pipeline — populates job descriptions
python main.py --no-discover

# User ingestion API
uvicorn api.server:app --reload

# Reset test jobs (PowerShell)
docker exec persift-db psql -U persift -d persift -c "UPDATE user_jobs SET status='applying', failure_reason='' WHERE job_id='8004171';"
docker exec persift-db psql -U persift -d persift -c "UPDATE user_jobs SET status='applying', failure_reason='' WHERE job_id='5099422007';"

# Reset extension state (Service Worker console)
chrome.storage.local.set({phase:'idle', current_job:null, current_tab_id:null, phase_started_at:null, user_id:'46e66cfa-e625-4ffc-b8dc-7bf75e21db26'}, ()=>console.log('reset'))

# Trigger test cycle (Service Worker console)
runPollCycle()
```

---

## Environment Variables (.env)

```
OPENAI_API_KEY=          # not set — Layer 4 disabled until Anthropic key arrives
ANTHROPIC_API_KEY=       # incoming — will enable L4 in rewriter.py (3-line swap)
SLACK_WEBHOOK_URL=
POLL_INTERVAL_MINUTES=10
LOG_LEVEL=INFO
DATABASE_URL=postgresql://persift:persift@localhost:5432/persift
RENDER_DATABASE_URL=     # external Render Postgres URL
```

---

## Test Data

- Test user ID: `46e66cfa-e625-4ffc-b8dc-7bf75e21db26`
- Test user email: `himanshujar911@gmail.com`

| job_id | ATS | Company | URL | Status |
|---|---|---|---|---|
| 5153686008 | greenhouse | Geotab (InternshipList) | https://job-boards.greenhouse.io/internshiplist2000/jobs/5153686008 | FULLY CONFIRMED ✓ |
| 8004171 | greenhouse | OfferUp | https://job-boards.greenhouse.io/offerup/jobs/8004171 | CONFIRMED ✓ |
| 8403219002 | greenhouse | SpaceX | https://job-boards.greenhouse.io/spacex/jobs/8403219002 | SKIPPED — ITAR |
| 5099422007 | greenhouse | Verkada | https://job-boards.greenhouse.io/verkada/jobs/5099422007 | IN PROGRESS |
