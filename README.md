# Persift

Persift is the outcome data layer for early-career hiring. Students get autonomous job applications. We collect labeled training data — every application, outcome, and user-job interaction — that compounds into the most valuable dataset in early-career hiring.

**One-sentence pitch:** Persift is building the outcome dataset for early-career hiring. Students get autonomous job applications. We get labeled training data — and a self-expanding map of who's hiring — that nobody else has.

---

## What It Does

1. **Discovers jobs** — polls 6,000+ companies across Greenhouse, Ashby, Lever, SmartRecruiters, and the Jobright aggregator (~48K intern roles) on a continuous schedule
2. **Filters and deduplicates** — intern/entry-level detection, dedup against Postgres, enrichment into a consistent schema
3. **Matches jobs to users** — 6 hard filters (work auth, graduation date, preferences) + semantic scoring via sentence-transformers
4. **Tailors resumes** — keyword injection, LLM bullet rewrite, ATS formatting check — per job, per user
5. **Auto-applies** — Chrome extension fills and submits Greenhouse applications autonomously
6. **Collects outcomes** — every application labeled with downstream results (callback, interview, offer, ghost, rejection)

---

## Architecture

```
[Render — discovery_runner.py]
  Jobright poller (hourly) → discovery_staging
  Worker A (every 90 min) → slug matching → known companies marked, unknowns queued for review

[Full pipeline — main.py, not yet on Render]
  poll_all() → detect → enrich → match → tailor → notify Slack
  Chrome extension → auto-apply → outcome collection
```

**Database:** Postgres (asyncpg). 6,082 companies seeded across 5 ATSes.

**Render deployment:** Discovery pipeline live. Full pipeline pending.

---

## Repository Map

| Path | Purpose |
|---|---|
| `main.py` | Full pipeline orchestrator. APScheduler — polling, matching, tailoring, nightly cleanup |
| `discovery_runner.py` | Render entry point. Jobright poller + Worker A only |
| `config.py` | All constants and env config |
| `db.py` | asyncpg connection pool and shared DB helpers |
| `api/server.py` | FastAPI user ingestion API |
| `pollers/` | Greenhouse, Ashby, Lever, SmartRecruiters, Jobright, Workday, Custom pollers |
| `pipeline/` | detector → enricher → scorer → injector → rewriter → formatter → matcher → tailor_worker → discovery_worker |
| `migrations/` | Postgres migration files (001–013) |
| `extension/` | Chrome extension — Manifest V3, Greenhouse form filler, popup UI |
| `scripts/seed_companies.py` | One-time seed script. Already run — do not run again |
| `discover_companies.py` | Monthly CDX crawl to expand company slug lists |

---

## How to Run

```bash
# Start Postgres
docker compose up -d

# Discovery pipeline only (Render target)
python discovery_runner.py

# Full pipeline (not yet — wait for Render deployment)
python main.py --no-discover

# User ingestion API
uvicorn api.server:app --reload
```

---

## Environment Variables

```
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
SLACK_WEBHOOK_URL=
POLL_INTERVAL_MINUTES=10
LOG_LEVEL=INFO
DATABASE_URL=postgresql://persift:persift@localhost:5432/persift
```

---

## Dependencies

```bash
pip install asyncpg fastapi uvicorn httpx sentence-transformers openai anthropic \
            python-docx pdfplumber psycopg2-binary apscheduler python-dotenv weasyprint
```

---

## Status

- Discovery pipeline: live on Render (Jobright + Worker A)
- Chrome extension: Greenhouse auto-fill complete
- Full pipeline (matcher + tailor): built, not yet on Render
- Beta: not yet open
