# Persift — Claude Code Context

Persift is the outcome data layer for early-career hiring. Students get autonomous job applications. We collect labeled training data — every application, outcome, and user-job interaction — that compounds into the most valuable dataset in early-career hiring. Eventually, employers pay for the hiring signal that data produces.

The product surface the user sees: install Chrome extension, build profile, system finds and applies to relevant jobs automatically. The strategic identity: a data company building two proprietary flywheels — outcome data and user-driven job discovery data.

---

## Codebase Map

| File / Folder | What it does |
|---|---|
| `main.py` | Orchestrator. Scheduler, company list loading from DB (30-min refresh cycle), polling cycles, seed mode, nightly cleanup job |
| `config.py` | All config and constants. Reads from `.env`. Single source of truth. Includes SCORER_MODEL_VERSION, REWRITER_MODEL_VERSION, PIPELINE_VERSION |
| `db.py` | DB abstraction — asyncpg connection pool. Public functions: init_db, filter_new_ids, mark_seen_batch, increment_consecutive_failures, reset_consecutive_failures |
| `discover_companies.py` | CLI tool. Monthly CDX crawl to expand ATS slug lists. Writes to both JSON files AND companies table (Fix 2 complete). _upsert_companies_to_db() added. |
| `discovery_runner.py` | Slim Render scheduler. Runs Jobright poller (60 min) + Worker A (90 min) only. No matcher, tailor, or API. Entry point for Render deployment. |
| `api/server.py` | FastAPI user ingestion API. POST /users, GET /health, GET /jobs/{job_id}/resume, GET /jobs/queue, GET /jobs/queue/count, POST /jobs/{job_id}/applied, POST /jobs/{job_id}/failed |
| `pollers/greenhouse.py` | Polls Greenhouse boards API. 2,127 companies. consecutive_failures wired. |
| `pollers/ashby.py` | Polls Ashby posting API. 2,767 companies. consecutive_failures wired. |
| `pollers/lever.py` | Polls Lever postings API. 303 companies. consecutive_failures wired. |
| `pollers/smartrecruiters.py` | Polls SmartRecruiters API. 885 companies. 3-page cap, 6-slug blacklist. consecutive_failures wired. |
| `pollers/workday.py` | Polls Workday tenant APIs. Being phased out — Jobright covers these |
| `pollers/jobright.py` | Polls Jobright aggregator API. 22 intern categories, hourly, ~48K+ jobs. fetch_jd() for lazy JD fetching. NOTE: apply_url is NOT returned by the bulk API or jobs/info without auth. |
| `pollers/custom.py` | Config-driven poller for custom company APIs |
| `pollers/filter.py` | Shared filtering: is_intern_role(), is_entry_level(), assign_categories(), matches_title() |
| `pipeline/detector.py` | Dedup against DB. Marks new jobs as seen |
| `pipeline/enricher.py` | Normalizes raw poller output into consistent shape |
| `pipeline/scorer.py` | Layer 1+2: keyword extraction (pure Python) + relevance scoring (sentence-transformers all-MiniLM-L6-v2) |
| `pipeline/injector.py` | Layer 3: keyword injection into resume skills section. JSON-backed tech term list |
| `pipeline/rewriter.py` | Layer 4: LLM bullet rewrite via OpenAI GPT-4o. Migrating to Claude API when credits available |
| `pipeline/formatter.py` | Layer 5: ATS formatting check. 5 checks: word count, section headers, single column, no tables, no page numbers |
| `pipeline/tailor_worker.py` | Tailor worker: processes queued user_jobs through Layers 3-5. Pro users first, Semaphore(5). Outputs .txt and .pdf. Now populates resume_text_snapshot, tailored_resume_text, resume_snapshot_id. |
| `pipeline/matcher.py` | Matching engine: pairs new jobs to users via 6 hard filters + scoring. Runs every 6 minutes. Lazy Jobright JD fetch. Now populates ML snapshot fields and model_predictions. |
| `pipeline/notifier.py` | Slack Block Kit notification sender. notify_excluded_company() for amber excluded-company alerts. |
| `pipeline/discovery_worker.py` | Worker A v1.1.0. Slug matching → career page fingerprinter → companies table. Fetches dataSource.companyResult.companyURL from Jobright __NEXT_DATA__, tries /careers /jobs /career /join /work-with-us, greps HTML for ATS signatures, inserts discovered companies with match_method='career_page_fingerprint'. |
| `migrations/` | SQL migration files. Run in order against Postgres. 001-013 complete. |
| `scripts/seed_companies.py` | One-time seed script. Already run — 6,082 companies in DB. Do not run again. |
| `Dockerfile.discovery` | Slim Docker image for Render. No WeasyPrint, no sentence-transformers. Deps: asyncpg httpx psycopg2-binary apscheduler python-dotenv. |
| `render.yaml` | Render blueprint. type: web (free tier), plan: free Postgres. Wires DATABASE_URL automatically. |
| `extension/manifest.json` | Chrome extension manifest V3. |
| `extension/background.js` | Event-driven state machine service worker. |
| `extension/api.js` | Shared backend API module. |
| `extension/content/greenhouse.js` | Greenhouse form filler. |
| `extension/popup/popup.html` | Extension popup HTML. 6 states. |
| `extension/popup/popup.js` | Popup state renderer. |
| `extension/popup/popup.css` | Popup styles. Dark warm theme. |
| `extension/icons/` | icon16/32/48/128.png — Persift P mark logo |

---

## Strategic Identity (locked May 26, 2026)

Persift is the outcome data layer for early-career hiring. The auto-apply product is the wedge. The real value is two compounding datasets:

1. **Outcome dataset**: every application labeled with downstream results (callback, interview, offer, ghost, rejection). After 100K applications this is irreplaceable — competitors cannot backfill historical outcome data.

2. **Discovery dataset**: every job a user browses, clicks, saves, or pastes becomes job-discovery signal. After 500 active users this compounds independently of the outcome dataset.

The endgame: employers pay $4K-$30K per hire for hiring signal derived from this data. The student wedge is how we earn the right to build the candidate graph.

One-sentence pitch: "Persift is building the outcome dataset for early-career hiring. Students get autonomous job applications. We get labeled training data — and a self-expanding map of who's hiring — that nobody else has."

**Competitor context (May 30):** Tsenta (YC S26) — desktop app, on-device, 50K+ career pages, 12 ATSes, $9.99/mo Pro, 55K monthly visits. Key weakness: on-device architecture cannot collect outcome data centrally. Persift's data flywheel thesis is structurally impossible for Tsenta to replicate.

---

## Current Pipeline State

```
[discovery_runner.py — Render entry point]
poll_jobright() → dedup → INSERT discovery_staging (company_name, no apply_url)
                                          ↓
                    [every 90 min] run_discovery_cycle() — Worker A v1.1.0
                    → Step 1: exact company_name match (fast-path, now active after 6,082-row backfill)
                    → Step 2: slug candidates (4 variants, ~10% hit rate)
                    → Step 3: fetch Jobright jobs/info/{jobId} __NEXT_DATA__
                              → dataSource.companyResult.companyURL → domain
                    → Step 4: try /careers /jobs /career /join /work-with-us
                    → Step 5: grep HTML for ATS signatures
                              → polled ATS (ashby/greenhouse/lever/smartrecruiters):
                                  INSERT companies (discovered_via='fingerprint') → result='added'
                              → unpolled ATS (workday/bamboohr/jobvite):
                                  queue_manual_review (bucket='known_ats_unclear_slug')
                              → no signature / no career page / no domain:
                                  queue_manual_review (bucket='unknown_ats')

[main.py — full pipeline, NOT on Render, crashes locally on Windows]
poll_all() → detect_new_jobs() → enrich() → notify_slack()
                                                    ↓
                                    [every 6 min] run_matching_cycle()
                                    (never run yet — 0 user_jobs, 1 user, 18,147 jobs in DB)
                                                    ↓
                                    [every 10 min] run_tailor_cycle()
                                    (broken locally: weasyprint not installed on Windows)
                                                    ↓
                                    [Chrome extension] auto-apply
                                    (queue always empty — tailor never sets status='applying')
                                                    ↓
                                    [3AM daily] run_cleanup_job()
```

**DB snapshot (June 1, 2026):** 1 pro user | 18,147 jobs (greenhouse: 744, ashby: 514, lever: 119, smartrecruiters: 614, jobright: 8,642, workday: 7,245, custom: 269) | 0 user_jobs | 6,082 companies seeded

**IMPORTANT: Do not run the full pipeline (main.py) until the discovery pipeline is live on Render.**

**LOCAL WINDOWS NOTE:** `main.py` crashes on import — `weasyprint` requires GTK/Cairo on Windows. Works on Render Linux. To fix locally: `pip install weasyprint --break-system-packages` (may still need GTK). Render Dockerfile.discovery excludes weasyprint by design.

---

## Jobright API — Critical Notes (updated June 1, 2026)

- Bulk API (`swan/mini-sites/list` POST): returns jobId, tabCategory, postedAt, properties (title, company, location, salary, workModel, industry, companySize, qualifications, h1bSponsored). **NO apply_url, NO domain.**
- `jobs/info/{jobId}` unauthenticated **__NEXT_DATA__**: apply_url is auth-gated and **not in `__NEXT_DATA__` at all**. The `source` field (e.g. value `1`) is **not a reliable ATS enum** — maps to Ashby, Oracle, Workday all the same.
- `jobs/info/{jobId}` unauthenticated **DOES** return `companyResult.companyURL` (company website). **Correct JSON path: `props.pageProps.dataSource.companyResult.companyURL`** — NOT `props.pageProps.jobResult.companyResult.companyURL` (that key is empty).
- GitHub repos (36 public): markdown mirrors of jobright.ai. No apply URLs.
- **Conclusion on apply_url:** Cannot get ATS apply URLs from Jobright without authentication. Use company domain fingerprinting instead.
- **Conclusion on domain:** `dataSource.companyResult.companyURL` works unauthenticated. Worker A v1.1.0 uses this as the fingerprinting entry point.

---

## Postgres Schema

### users
`id UUID PK`. `tier TEXT` CHECK ('free', 'pro'). `preferences JSONB`. `work_auth JSONB`. `resume_text TEXT`. `application_settings JSONB`.
Structured columns: `requires_sponsorship BOOLEAN`, `work_auth_type TEXT`, `available_start_date DATE`, `university TEXT`, `graduation_date DATE`, `major TEXT`, `cohort_signup_week DATE`.

### jobs
Composite PK: `(job_id, ats)`. `categories TEXT[]` with GIN index. `sources TEXT[]`. `posted_at BIGINT` (ms epoch).
New: `jd_structured JSONB`, `jd_captured_at TIMESTAMPTZ`, `last_seen_at TIMESTAMPTZ`, `estimated_fill_date TIMESTAMPTZ`, `extractor_version TEXT`.

### companies
`id SERIAL PK`. `canonical_company_id UUID NOT NULL`. `slug TEXT NOT NULL`. `ats TEXT NOT NULL`. UNIQUE: `(slug, ats)`. `is_active BOOLEAN`. `consecutive_failures INT`.
New: `canonical_domain TEXT`, `industry TEXT`, `headcount_range TEXT`, `discovered_via TEXT`, `discovered_at TIMESTAMPTZ`, `posting_velocity NUMERIC`, `match_method TEXT`, `match_confidence TEXT`, `company_name TEXT`.

**6,082 companies seeded. 5,975 unique canonical_company_ids.**

### discovery_staging
`id SERIAL PK`. `job_id TEXT NOT NULL`. `job_ats TEXT NOT NULL`. `company_name TEXT`. `apply_url TEXT`. `staged_at TIMESTAMPTZ DEFAULT NOW()`. `processed BOOLEAN DEFAULT FALSE`. `processed_at TIMESTAMPTZ`. `result TEXT` CHECK ('added','already_known','queued_manual','failed'). `result_canonical_company_id UUID`. `worker_version TEXT`. UNIQUE: `(job_id, job_ats)`.
Partial index on unprocessed rows. Cascades to manual_review_queue.

### manual_review_queue
Created by Worker A on startup (CREATE IF NOT EXISTS). `id SERIAL PK`. `apply_url TEXT`. `company_name TEXT`. `staged_job_id INT FK → discovery_staging`. `bucket TEXT` CHECK ('known_ats_unclear_slug','unknown_ats'). `created_at TIMESTAMPTZ`. `resolved BOOLEAN DEFAULT FALSE`.

### resume_snapshots
`id SERIAL PK`. `user_id UUID FK`. `version_number INT`. `resume_text TEXT`. `resume_structured JSONB`. `is_active BOOLEAN`.

### user_jobs
`id SERIAL PK`. UNIQUE: `(user_id, job_id, job_ats)`. Status, ML columns, trigger-maintained `current_stage`.

### application_outcomes
APPEND-ONLY. `outcome_type TEXT` (applied_confirmed through offer_expired). Correction chain via `corrects_outcome_id`.

### model_predictions, gmail_authorizations, gmail_signals, user_job_interactions, aggregate_benchmarks, company_merge_candidates
(unchanged from May 26 doc)

### poller_state
Stores `cursor JSONB` per poller name. Used by discovery_runner.py to track Jobright `since_ms`.

---

## Key Config Values

| Constant | Value | Notes |
|---|---|---|
| DATABASE_URL | `postgresql://persift:persift@localhost:5432/persift` | Swap for Render internal URL in prod |
| POLL_INTERVAL_MINUTES | 10 | Tier 1 polling frequency |
| OPENAI_MODEL | `gpt-4o` | Migrating to claude-sonnet-4-20250514 when credits available |
| SCORER_MODEL_VERSION | `all-MiniLM-L6-v2-v1` | Tagged on all model_predictions rows |
| PIPELINE_VERSION | `1.0.0` | Tagged in feature_snapshot JSONB |

---

## Discovery Pipeline Design (June 1, 2026)

**Goal:** Self-expanding company → ATS mapping database. Jobright feeds company names continuously. Worker A resolves each to an ATS + slug and adds it to the polling list, forever, on Render.

Worker A v1.1.0 detection cascade:
1. Exact `company_name` match (case-insensitive) — ACTIVE, fast-path (6,082 rows backfilled June 1)
2. Slug candidates from company name (4 variants, hyphenated + concatenated, with/without suffixes) — ACTIVE (~10% hit rate)
3. Fetch `jobs/info/{jobId}` → parse `__NEXT_DATA__` → `dataSource.companyResult.companyURL` — ACTIVE
4. Try `/careers`, `/jobs`, `/career`, `/join`, `/work-with-us` on that domain — ACTIVE
5. Grep HTML for ATS fingerprints → extract slug from embedded ATS URLs — ACTIVE
   - Polled ATS match → INSERT companies, result='added'
   - Unpolled ATS (workday/bamboohr/jobvite) → manual_review_queue, bucket='known_ats_unclear_slug'
   - No signature / SPA → manual_review_queue, bucket='unknown_ats'
6. BuiltWith paid API — August, $295/month (solves SPAs)

**Tiered resolution strategy:**
- Tier 1: Static HTML fingerprint (free, built, runs on Render) → catches ~30% of companies
- Tier 2: CommonCrawl DuckDB batch query (free, needs AWS creds — support case submitted June 1) → catches SPA companies whose career pages CommonCrawl has already crawled
- Tier 3: BuiltWith API (August, $295/mo) → catches everything remaining

**First run results (May 30):** 8,642 companies analyzed | 849 already_known | 7,793 queued for review

**Slug matching gaps identified (June 1):**
- `company_name` column was NULL for all seeded rows — Step 1 never fired. Fixed via backfill.
- Step 2 is exact match only — no fuzzy/trigram. Misses abbreviations (IBM), trade names (Google/Alphabet), ATS-specific short slugs.
- Improvement path: pg_trgm similarity on slug, reverse slug-to-name comparison, expand suffix strip list.

---

## Discovery Pipeline — Investigation Log (June 1, 2026)

### What we investigated

**Jobright bulk API field dump** (confirmed via debug print on first job object):
```json
{ "jobId": "...", "tabCategory": ["intern:us:human_resources"], "postedAt": 1780312896000,
  "properties": { "title", "company", "location", "salary", "workModel", "industry": ["Hospital"],
                  "companySize": "1001-5000", "qualifications", "expLevel", "jobFunction",
                  "h1bSponsored", "isNewGrad", "roleType", "hireTime", "graduateTime" } }
```
No `apply_url`, no `domain`, no `website`. `industry` and `companySize` are new fields we weren't capturing — now stored in bulk result.

**Jobright jobs/info/{jobId} __NEXT_DATA__ structure** (confirmed on BillGO, jobId: `69ba46703b74eb1e2c8835f3`):
- Correct path: `props.pageProps.dataSource.companyResult.companyURL` → `"https://www.billgo.com"`
- Wrong path previously assumed: `props.pageProps.jobResult.companyResult` → empty dict `{}`
- `dataSource` also contains: companyName, companySize, companyDesc, companyCategories, companyTwitterURL, companyLinkedinURL, companyCrunchbaseURL, companyFoundYear, companyLocation, fundraisingCurrentStage, fundraisingTotalFunding, leadership, pressReferences, h1bAnnualJobCount, isAgency

**Worker A fingerprinting test (5 rows from manual_review_queue, June 1):**
| Company | Domain | Career Page | ATS | Result |
|---|---|---|---|---|
| Kwest Group | kwestgroup.com | Not found (all 5 paths 404) | — | skipped |
| RemoteHunter | remotehunter.com | /jobs (26K chars) | None (custom board) | unknown_ats |
| BillGO | billgo.com | /careers (90K chars) | None (SPA, ATS loads after JS) | unknown_ats |
| Alston & Bird | alston.com | /careers (31K chars) | workday (wd1, via myworkdayjobs.com link) | known_ats_unclear_slug |

Key finding: static HTML fingerprinter catches companies with server-rendered ATS embeds. SPAs where the ATS widget loads after JS render are missed — this is the majority of modern career pages.

**CommonCrawl investigation:**
- CDX API (`index.commoncrawl.org`): consistently 504s for CC-MAIN-2026-21 (too new, under load). Older crawls also 504. Not viable for real-time single-company lookups.
- Columnar index parquet on S3: correct architecture for bulk queries. `s3://commoncrawl/cc-index/table/cc-main/warc/crawl=CC-MAIN-2026-21/subset=warc/*.parquet`. DuckDB anonymous S3 access fails with 403 — requires AWS credentials even for public bucket.
- S3 directory listing: blocked (403 on both path-style and bucket-style endpoints).
- AWS account ID 496006843764 is currently suspended. Support case submitted June 1, 2026.
- CommonCrawl is the right Tier 2 solution once credentials are restored.

**Pipeline status audit (June 1):**
- All pollers: import clean, work correctly.
- Detector, enricher, scorer, injector, notifier, matcher, api.server: all import clean, no bugs found.
- `main.py`: crashes on import — `tailor_worker.py` does `from weasyprint import HTML` at module level. weasyprint not installed on Windows. All other imports succeed.
- `rewriter.py`: `openai` package installed but `OPENAI_API_KEY` not set → silently returns un-rewritten resume. Layer 4 effectively disabled.
- `matcher.py`: never run. 0 rows in `user_jobs`. Needs a fresh poll cycle (jobs WHERE first_seen_at > NOW() - 6min) after main.py is fixed.
- Extension: BASE_URL hardcoded to localhost. Content scripts only cover Greenhouse. No Ashby/Lever/SmartRecruiters scripts exist.

---

## Pending Work (Next Session)

| Priority | Task | Status |
|---|---|---|
| 1 | Check Jobright API for company website/domain field | **DONE** — bulk API has no domain; jobs/info/{jobId} __NEXT_DATA__ dataSource.companyResult.companyURL works unauthenticated |
| 2 | Build company domain fingerprinting in Worker A | **DONE** — Worker A v1.1.0 built and tested. Static HTML fingerprinter live. |
| 3 | Deploy to Render — run migrations 001-013 against Render Postgres | Pending |
| 4 | Internal dashboard for manual_review_queue | Pending |
| 5 | Cybersecurity deep dive with Opus (before beta users) | Pending — HIGH, required before any real user |
| 6 | Gmail scanner design (after cybersecurity) | Pending |
| 7 | Fix weasyprint locally — main.py import crash on Windows | Pending — Render unaffected |
| 8 | Set OPENAI_API_KEY or swap rewriter.py to Claude API (claude-sonnet-4-6, 3-line change) | Pending — Layer 4 silently disabled without it |
| 9 | Build Ashby content script — highest impact (514 companies, clean API-based forms) | Pending |
| 10 | Build Lever and SmartRecruiters content scripts | Pending (after Ashby) |
| 11 | Update BASE_URL in extension/api.js to production URL before any real user | Pending |
| 12 | Await AWS support response — unblocks CommonCrawl Tier 2 batch worker | Pending — account suspended, case submitted June 1 |
| 13 | README rewrite — describes old SQLite/DynamoDB architecture, no Chrome extension, no data flywheel | Pending — required before beta outreach |

---

## Known Issues (updated June 1, 2026)

| Issue | Severity | Notes |
|---|---|---|
| apply_url always NULL in discovery_staging | HIGH | Jobright auth-gates it. Fingerprinting pipeline uses domain instead — this is by design now |
| Worker A added count: 0 on first run | RESOLVED | Was blocked by NULL company_name. Fixed: 6,082 rows backfilled June 1. Fingerprinter now active. |
| Render not deployed yet | HIGH | Blueprint ready. Run migrations 001-013 against Render Postgres first |
| main.py crashes on import — Windows only | HIGH | weasyprint not installed. `from weasyprint import HTML` at module level in tailor_worker.py. Works on Render Linux. |
| OPENAI_API_KEY not set | Medium | Layer 4 (LLM rewrite) silently no-ops — pro users get L3 injection only |
| AWS account suspended | HIGH | Blocks CommonCrawl Tier 2. Support case submitted June 1. Account ID: 496006843764. |
| BASE_URL hardcoded to localhost in extension/api.js | HIGH | Must point to production URL before any real user can install extension |
| Content scripts only cover Greenhouse | HIGH | Ashby, Lever, SmartRecruiters content scripts don't exist — 3 of 4 polled ATSes can't be auto-applied |
| host_permissions only covers localhost + greenhouse.io | HIGH | Chrome blocks extension requests to any other ATS domain |
| Extension queue always empty | HIGH | weasyprint crash prevents tailor from advancing user_jobs status to 'applying' — extension has nothing to process |
| Matcher never run | HIGH | 0 rows in user_jobs. 1 pro user, 18,147 jobs in DB. Needs main.py running with a fresh poll cycle. |
| SPA career pages missed by fingerprinter | Medium | ATS widget loads after JS render — static HTML fetch finds no signature. Tier 2 (CommonCrawl) and Tier 3 (BuiltWith) solve this. |
| httpx logging at INFO level | Low | Floods terminal — set to WARNING |
| Behavioral simulation basic | Medium | Mouse trajectories not fully implemented — Phase 2 |
| Layer 4 essay generation not built | Medium | Extension skips essay questions — Phase 2 |
| OpenAI → Claude API swap pending | Low | Waiting on Anthropic credits. 3-line change in rewriter.py. |
| Cybersecurity review not done | HIGH | Required before any beta users |
| Gmail scanner not built | — | After cybersecurity review |
| README.md is completely stale | HIGH | Describes old SQLite/DynamoDB single-user architecture, no Chrome extension, no data flywheel. Must be rewritten before any beta outreach. |

---

## Design System (Locked May 25, 2026)

**Direction:** Editorial Quiet Confidence.

**Colors:**
| Token | Value |
|---|---|
| Background | #1a1816 |
| Surface | #221f1c |
| Border | #2d2a26 |
| Text primary | #faf8f5 |
| Text secondary | #d4cfc4 |
| Text muted | #8a857d |
| Green | #97C459 |
| Amber | #EF9F27 / #FAC775 |

**Typography:** Source Serif 4 + Inter. Upgrade to GT Sectra + Sohne Mono when revenue available.

---

## How to Run

```bash
# Start Postgres (required first)
docker compose up -d

# Discovery pipeline only (for Render)
python discovery_runner.py

# Full pipeline (when ready — do not run before Render deployment)
python main.py --no-discover

# User ingestion API
uvicorn api.server:app --reload

# Backfill discovery_staging from existing jobs table
# (run in PowerShell against local Docker)
echo "INSERT INTO discovery_staging (job_id, job_ats, company_name, apply_url) SELECT job_id, ats, company_name, apply_url FROM jobs WHERE ats = 'jobright' ON CONFLICT (job_id, job_ats) DO NOTHING;" | docker exec -i persift-db psql -U persift -d persift

# Reset Jobright timestamp (force full re-fetch)
echo "DELETE FROM poller_state WHERE poller = 'jobright';" | docker exec -i persift-db psql -U persift -d persift
```

---

## Environment Variables (.env)

```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=          # not yet set
SLACK_WEBHOOK_URL=
POLL_INTERVAL_MINUTES=10
LOG_LEVEL=INFO
DATABASE_URL=postgresql://persift:persift@localhost:5432/persift
```

---

## Dependencies

```bash
pip install weasyprint --break-system-packages
pip install asyncpg fastapi uvicorn httpx sentence-transformers openai anthropic python-docx pdfplumber psycopg2-binary apscheduler python-dotenv
```

---

## LinkedIn Build-in-Public Status

| Post | Status |
|---|---|
| Post 1 (IBM rejection story) — 1,212 impressions | Done |
| Post 2 (800 apps, 0 interviews) — 8,146 impressions | Done |
| Post 3 (interview empathy post) | Done |
| Post 4 (Microsoft pipeline post) | Done |
| Post 5 (referral filled headcount) | Done |
| May 30 — 5am idea, 7,793 companies identified | READY TO POST |
| May 31 — Empty apartment moving out | Planned |
| June 1 — Seattle landing | Today |
| June 7-10 — Introduce Persift by name | Planned |
| June 21+ — Beta waitlist | Planned |