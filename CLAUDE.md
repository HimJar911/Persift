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
| `pipeline/discovery_worker.py` | Worker A. Reads discovery_staging, runs slug matching cascade, queues unknown companies for manual review. Loops all unprocessed rows in batches of 500. Clean print() output. |
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
                    [every 90 min] run_discovery_cycle()
                    → slug candidate matching (4 variants from company name)
                    → already_known: mark processed
                    → queued_manual: insert manual_review_queue
                    → added: 0 (blocked — no apply_url/domain for fingerprinting)

[main.py — full pipeline, not on Render yet]
poll_all() → detect_new_jobs() → enrich() → notify_slack()
                                                    ↓
                                    [every 6 min] run_matching_cycle()
                                                    ↓
                                    [every 10 min] run_tailor_cycle()
                                                    ↓
                                    [Chrome extension] auto-apply
                                                    ↓
                                    [3AM daily] run_cleanup_job()
```

**IMPORTANT: Do not run the full pipeline (main.py) until the discovery pipeline is live on Render.**

---

## Jobright API — Critical Notes (May 30)

- Bulk API (`swan/mini-sites/list` POST): returns jobId, tabCategory, properties (title, company, location, salary, h1bSponsored), postedAt. **NO apply_url.**
- `jobs/info/{jobId}` endpoint: returns "Original Job Post" link ONLY when logged in. Unauthenticated = no apply URL.
- GitHub repos (36 public): markdown mirrors of jobright.ai. No apply URLs. Updated hourly.
- **Conclusion:** Cannot get apply URLs from Jobright without authentication. Discovery pipeline uses company name slug matching instead.
- **Next step:** Check if company website/domain is available in any Jobright response field. If yes, build domain fingerprinting.

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

## Discovery Pipeline Design (partially built)

Worker A detection cascade:
1. URL pattern matching — SUSPENDED (no apply_url available from Jobright)
2. Career page fingerprinting — SUSPENDED (no domain available)
3. Company name → slug candidates — ACTIVE (4 variants, ~10% hit rate)
4. Manual review queue — ACTIVE (bucket = 'unknown_ats')
5. BuiltWith paid API — August, $295/month

**First run results (May 30):** 8,642 companies analyzed | 849 already tracked | 7,793 queued for review

**Pending before fingerprinting can work:**
- Confirm whether company website domain is in any Jobright API response
- If yes: build domain fingerprinting in Worker A
- If no: explore alternative data sources for company domains

---

## Pending Work (Next Session)

| Priority | Task |
|---|---|
| 1 | Check Jobright API for company website/domain field |
| 2 | Build company domain fingerprinting in Worker A |
| 3 | Deploy to Render — blueprint ready, run migrations against Render Postgres |
| 4 | Internal dashboard for manual_review_queue |
| 5 | Cybersecurity deep dive with Opus (before beta users) |
| 6 | Gmail scanner design (after cybersecurity) |

---

## Known Issues (May 30)

| Issue | Severity | Notes |
|---|---|---|
| apply_url always NULL in discovery_staging | HIGH | Jobright auth-gates it. Need domain fingerprinting instead |
| Worker A added count always 0 | HIGH | Blocked by above |
| Render not deployed yet | HIGH | Blueprint ready. Run migrations against Render Postgres first |
| Debug log lines in discovery_runner.py | Low | apply_url debug prints — remove before next real run |
| httpx logging at INFO level | Low | Floods terminal — set to WARNING |
| Extension not fully tested | Medium | States 1, 4, 5 require jobs in queue |
| Behavioral simulation basic | Medium | Mouse trajectories not fully implemented — Phase 2 |
| Layer 4 essay generation not built | Medium | Extension skips essay questions — Phase 2 |
| OpenAI → Claude API swap pending | Low | Waiting on Anthropic credits |
| Cybersecurity review not done | HIGH | Required before any beta users |
| Gmail scanner not built | — | After cybersecurity review |
| README.md is completely stale | HIGH | Describes old SQLite/DynamoDB single-user architecture, mentions Jobvite, no Chrome extension, no data flywheel. Must be rewritten before any beta outreach or LinkedIn posts that link to the repo |

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
| June 1 — Seattle landing | Planned |
| June 7-10 — Introduce Persift by name | Planned |
| June 21+ — Beta waitlist | Planned |