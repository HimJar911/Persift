# Persift — Claude Code Context

> **Active launch plan:** See `LAUNCH_PLAN.md` (at C:\Users\himan\Desktop\Persift\LAUNCH_PLAN.md) for the locked day-by-day build plan. Hard launch date: July 15, 2026. Tech week pitch: July 27, 2026. All session work should be checked against that plan first.

Persift is the outcome data layer for early-career hiring. Students get autonomous job applications and automatic tracking. Career centers get live visibility into student job searches and outcomes without self-reporting. Revenue comes from institutions (university career centers), not students.

---

## Strategic Identity (updated June 26, 2026)

**Two-sided product:**
- **Students (free):** Finds roles early (before LinkedIn), tailors resume, auto-applies, tracks automatically. Auto-submit unlocks after user manually reviews first 10 applications.
- **Career centers (paid):** Live visibility into what students are actually doing — applications sent, interviews converting, who's stuck — without waiting for self-reported surveys. Recurring institutional budget. Cohort refills every year so no churn.

**Competitor context:**
- Jobright: horizontal, consumer — won't follow into institutional vertical
- Tsenta (YC S26): on-device, can't centrally collect outcome data. Does cover Workday via Gmail OTP flow.
- 12Twenty/CareerLink: CRM for career centers, outcome data still self-reported via surveys. ASU just switched to it (June 2026).

**Outcome capture mechanism:** Apply-through exhaust + Gmail signal parsing for interview/rejection signals. Binary: interview or not-interview. Silence past 3-4 weeks = inferred rejection.

---

## Beta Launch Scope (locked June 26, 2026)

- **ATSes:** Greenhouse, Ashby, Lever, SmartRecruiters. Workday = post-launch v2.
- **Tailoring:** L1-L4 all enabled. Anthropic API key incoming. L4 swap point marked in rewriter.py.
- **Gmail tracking:** OAuth testing mode, 100 user cap, gmail.readonly + calendar.readonly. Interview/rejection signal detection. Start CASA audit at 80 users.
- **Infrastructure:** AWS (RDS + S3 + Cognito + ECS + Secrets Manager). Migrate off Render on Day 8 (July 3).
- **Frontend:** Next.js 14 App Router, TypeScript, Tailwind. Full build — 7-step onboarding, dashboard (3 panels), application detail, profile/settings. Unique visual identity separate from landing page.
- **Chrome Web Store:** Submit June 30. $5 developer fee.
- **Beta target:** 100 users.

---

## Current State (June 26, 2026)

### What's Working
- Greenhouse auto-fill confirmed on Geotab (job_id=5153686008) and OfferUp (job_id=8004171, immigration answer pending)
- All June 24 fixes are in the working tree but **NOT committed/pushed** — commit these before starting new work
- Discovery pipeline live on Render (Jobright polling every 60 min, Worker A every 90 min)
- Backend pipeline works locally. main.py --no-discover NOT YET RUN — all job descriptions still empty
- 18K+ jobs in DB, 6,082+ companies, 1 pro user, 2 user_jobs (test rows)

### Uncommitted Changes (working tree as of June 26)
These are all the June 24 session fixes sitting uncommitted:
- `api/server.py` — full profile fields in GET /users/{user_id}, _NeedsReviewReq model, POST /jobs/{job_id}/needs_review endpoint, base-resume fallback in GET /jobs/{job_id}/resume, CORSMiddleware added
- `extension/api.js` — markNeedsReview() added, BASE_URL on localhost:8000
- `extension/background.js` — DEBUG_MODE=true, closeTab() commented out in needs_review handler and checkStale()
- `extension/content/greenhouse.js` — all June 24 fixes (school combobox, state/country, phone country code, synonym fallbacks, handledLabels regex, sponsorship scoping, hardcoded ID removed)
- `extension/manifest.json` — updated host_permissions
- `main.py` — --check flag added
- `pipeline/rewriter.py` — WARNING log when OPENAI_API_KEY unset, TODO comment for Claude swap
- `pipeline/tailor_worker.py` — weasyprint lazy import
- `scripts/db_stats.py` — new file

**First thing tomorrow: commit all of these before touching anything else.**

---

## Day 1 Tasks (June 26 — TODAY)

- [ ] Commit all uncommitted working tree changes
- [ ] Add immigration support answer via update_profile.py (answer: "No")
- [ ] Re-run OfferUp test end-to-end, confirm all June 24 fixes hold
- [ ] Run main.py --no-discover — populate job descriptions, verify matching pipeline works
- [ ] Verify tailor worker advancing queued → applying correctly

---

## Codebase Map

| File / Folder | What it does |
|---|---|
| `main.py` | Orchestrator. Scheduler, company list loading from DB (30-min refresh cycle), polling cycles, seed mode, nightly cleanup job. --check flag added. --no-discover flag: runs without discovery. |
| `config.py` | All config and constants. Reads from `.env`. Single source of truth. Includes SCORER_MODEL_VERSION, REWRITER_MODEL_VERSION, PIPELINE_VERSION |
| `db.py` | DB abstraction — asyncpg connection pool. Public functions: init_db, filter_new_ids, mark_seen_batch, increment_consecutive_failures, reset_consecutive_failures |
| `discover_companies.py` | CLI tool. Monthly CDX crawl to expand ATS slug lists. Writes to both JSON files AND companies table. |
| `discovery_runner.py` | Slim Render scheduler. Runs Jobright poller (60 min) + Worker A (90 min) only. No matcher, tailor, or API. Health server on $PORT. |
| `api/server.py` | FastAPI user ingestion API. GET /users/{user_id} returns all profile fields including desired_hourly_min/max, custom_answers (parsed JSON), previous_employers (parsed JSON). POST /jobs/{job_id}/needs_review added. Base-resume fallback in GET /jobs/{job_id}/resume. CORSMiddleware allow_origins=["*"]. |
| `pollers/greenhouse.py` | Polls Greenhouse boards API. 2,127 companies. |
| `pollers/ashby.py` | Polls Ashby posting API. 2,767 companies. |
| `pollers/lever.py` | Polls Lever postings API. 303 companies. |
| `pollers/smartrecruiters.py` | Polls SmartRecruiters API. 885 companies. 3-page cap, 6-slug blacklist. |
| `pollers/jobright.py` | Polls Jobright aggregator API. 22 intern categories, ~48K+ jobs. |
| `pollers/filter.py` | Shared filtering: is_intern_role(), is_entry_level(), assign_categories(), matches_title() |
| `pipeline/detector.py` | Dedup against DB. |
| `pipeline/enricher.py` | Normalizes raw poller output. Populates description field on jobs. |
| `pipeline/scorer.py` | L1+L2: keyword extraction + relevance scoring (all-MiniLM-L6-v2). score_resume() → 0-100. |
| `pipeline/injector.py` | L3: keyword injection into resume skills section. |
| `pipeline/rewriter.py` | L4: LLM bullet rewrite. Currently disabled (no API key). WARNING log added. TODO comment marks 3-line Claude API swap point (claude-sonnet-4-6). |
| `pipeline/formatter.py` | L5: ATS formatting check. 5 checks. |
| `pipeline/tailor_worker.py` | Tailor worker: queued → applying. Pro users first, Semaphore(5). weasyprint lazy import. |
| `pipeline/matcher.py` | Matching engine. 6 hard filters + scoring. _SCORE_THRESHOLD = 50. |
| `pipeline/notifier.py` | Slack Block Kit notification sender. |
| `pipeline/discovery_worker.py` | Worker A v1.1.0. _BATCH_SIZE=50. |
| `migrations/` | SQL migration files. 001-014 complete. |
| `extension/manifest.json` | Chrome extension manifest V3. host_permissions: localhost:8000, *.greenhouse.io, boards.greenhouse.io, job-boards.greenhouse.io, *.ashbyhq.com. |
| `extension/background.js` | Service worker state machine. DEBUG_MODE=true (SET FALSE BEFORE PRODUCTION). closeTab() commented out (RESTORE BEFORE PRODUCTION). |
| `extension/api.js` | Shared API module. BASE_URL: localhost:8000 (REVERT TO AWS URL BEFORE PRODUCTION). markNeedsReview() added. |
| `extension/content/greenhouse.js` | Greenhouse form filler — see architecture section below. |
| `extension/content/ashby.js` | Ashby form filler. Not yet confirmed end-to-end. |
| `extension/popup/` | Popup HTML/JS/CSS. Needs redesign per launch plan. |
| `extension/TEST_COMMANDS.md` | Step-by-step test commands. |
| `insert_job.py` | Test utility — inserts job into user_jobs. |
| `update_profile.py` | Test utility — updates user profile fields in application_settings JSONB. |
| `scripts/db_stats.py` | DB stats script. |

---

## greenhouse.js — Architecture (as of June 24, 2026)

Fill order:
1. Basic fields — first_name, last_name, email, phone, linkedin, github, preferred_name, location_city
2. Resume upload — background.js fetches PDF (base64), content script converts to Blob via DataTransfer
3. Work auth — native select → radio → combobox → label scan. Added "eligible to work in the us", "work in the us on a long term" variants.
4. EEO — fillEeoField() tries direct ID, then combobox, then native select
5. Classifier sweep — FIELD_DEFS pattern matching with weights
6. Education — school ('school--0'), degree ('degree--0'), discipline ('discipline--0'), end-month/year — all comboboxes. School uses type-to-search approach (open, type 8 chars, wait for aria-controls, click match).
7. State & Country — findFieldByLabelText() with variants. Fills "Arizona, United States". Combobox fallback kept.
8. Phone country code — intl-tel-input library. Opens via button.iti__selected-country, listbox via [id$="__country-listbox"]. Must fill BEFORE phone number.
9. Internship duration checkboxes — reads from custom_answers "how long of an internship"
10. Graduation date text field — findNearText scan
11. Hourly compensation — midpoint of desired_hourly_min + desired_hourly_max. Multiple label variants.
12. Custom answers sweep — document-wide scan. getLabelForEl() + findCustomAnswer() fuzzy match. QUESTION_ALIASES for semantic variants. handledLabels regex skips already-filled fields.
13. Sponsorship — scoped to form only, checks divs with class*=field or class*=question. Added "immigration support", "immigration assistance" variants.
14. Submit or handoff — auto_submit=false sends needs_review (correct endpoint now)

**Key utilities:** fillText(), waitFor(), openReactSelect(), fillCombobox(), findComboboxByLabel(), findNearText(), findCustomAnswer(), getLabelForEl(), handledLabels regex, findFieldByLabelText()

**Known remaining issues:**
- getLabelForEl() returns empty for some text inputs (aria-labelledby not yet checked)
- School fill silently skips if aria-controls never populates (no fallback)
- Degree synonyms narrow (Undergraduate, BA, Bachelor of Arts not covered)
- Immigration support answer not yet in custom_answers profile (add via update_profile.py, answer: "No")

---

## Extension Architecture

**Full flow:**
1. poll_alarm fires every 5 min → fetchNextJob() → /jobs/queue?user_id=...
2. Gets job (status='applying') → opens URL in background tab
3. Tab loads → phase → 'filling'
4. Content script sends 'ready' → background.js fetches profile via getProfile() → responds with full context
5. Content script fills all fields, uploads resume PDF via background.js message passing
6. auto_submit=false → sends needs_review (marks DB status=needs_review via POST /jobs/{job_id}/needs_review), tab stays open
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
| email | himanshujar911@gmail.com (users.email column) |
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
| eeo_gender | Male |
| eeo_race | Asian |
| eeo_hispanic | false |
| eeo_veteran | I am not a protected veteran |
| eeo_disability | No, I do not have a disability and have not had one in the past |
| work_authorized | true |
| desired_hourly_min | 25 |
| desired_hourly_max | 40 |
| previous_employers | ["Johnson & Johnson", "Virtusa Corporation", "The Silicon Partners", "Arizona State University"] |
| custom_answers | 23-entry JSON array — immigration support answer PENDING (add "No") |

**custom_answers keys (23 entries):**
where did you hear about | how did you hear about this job opportunity | why do you want to work here | why are you interested in this role | tell us about yourself | what are your strengths | what is your greatest weakness | describe a challenge you faced | where do you see yourself in 5 years | what field are you looking to complete your internship | what term were you looking to start | how long of an internship are you looking for | will you consent to a background check | were you previously employed | are you available to work full time | are you able to commute | what is your expected date of graduation | what is your expected graduation | do you have experience with | are you currently enrolled | veteran of the armed forces | hourly compensation expectations | compensation expectations | cover letter

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

```bash
# Start Postgres
docker compose up -d

# Check imports clean
python main.py --check

# Full pipeline — live poll populates descriptions
python main.py --no-discover

# Matcher — all jobs
python -m pipeline.matcher --all

# User ingestion API
uvicorn api.server:app --reload

# PowerShell — load .env
Get-Content .env | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2]) } }

# Reset test job (PowerShell — no -it flag)
docker exec persift-db psql -U persift -d persift -c "UPDATE user_jobs SET status='applying', current_stage='applied', failure_reason='' WHERE job_id='5153686008';"

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
- Test job 1: job_id=5153686008, ats=greenhouse, apply_url=https://job-boards.greenhouse.io/internshiplist2000/jobs/5153686008 (Geotab — FULLY CONFIRMED)
- Test job 2: job_id=8004171, ats=greenhouse, apply_url=https://job-boards.greenhouse.io/offerup/jobs/8004171 (OfferUp — immigration answer pending)

**Reset SQL:**
```sql
UPDATE user_jobs SET status='applying', current_stage='applied', failure_reason='' WHERE job_id='5153686008';
UPDATE user_jobs SET status='applying', current_stage='applied', failure_reason='' WHERE job_id='8004171';
```
