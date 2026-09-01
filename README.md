# Persift

**A job-discovery and application-automation engine for early-career hiring.** Persift
continuously monitors company career pages across four applicant-tracking systems,
normalizes wildly inconsistent job data into a single schema, matches roles to a
candidate profile, tailors a resume per role, and auto-fills the application through a
Chrome extension.

This repository is a **portfolio archive** of a solo project. It is no longer under
active development, and the infrastructure that once ran it has been shut down. The
code is preserved as it ran in production.

---

## What it does

```
 discover ──▶ ingest ──▶ normalize ──▶ match ──▶ tailor ──▶ auto-apply ──▶ track outcome
```

1. **Discover** — crawls Common Crawl indexes to find companies hosting jobs on
   Greenhouse, Ashby, Lever, and SmartRecruiters, then fingerprints each company's ATS
   from its careers-page markup.
2. **Ingest** — polls every known company's job listing on a schedule. None of the four
   ATSes expose a delta/"since" API, so each poll re-fetches a company's entire current
   listing.
3. **Normalize** — turns per-ATS chaos (free-text country names, employer-configurable
   metadata arrays, inconsistent seniority signals) into consistent structured fields.
   See `pollers/seniority.py`, `pollers/geography.py`, `pollers/gh_metadata.py`.
4. **Match** — 6 hard filters (work authorization, graduation date, location, work
   model, category, years-of-experience) plus semantic scoring with
   `sentence-transformers`.
5. **Tailor** — per job, per user: keyword extraction, keyword injection, LLM bullet
   rewrite, ATS-format check. `pipeline/` layers L1–L5.
6. **Auto-apply** — a Manifest V3 Chrome extension (`extension/`) that classifies form
   fields, resolves values from the user profile, and fills real Greenhouse
   applications. A shared `filler_utils.js` (~1,200 lines) handles the DOM mechanics
   across React comboboxes, typeaheads, native selects, radio/checkbox groups, and
   international phone widgets.
7. **Track** — every application is labeled with its downstream outcome.

---

## Scale it operated at

| Metric | Figure |
|---|---|
| Company career pages monitored | 400,000+ (Common Crawl discovery surface) |
| Jobs indexed across 4 ATSes | 246,000+ (`jobs` table) |
| Greenhouse jobs in the working corpus | 20,837 |
| Form-field taxonomy entries harvested | 623,000+ |
| ATS platforms fingerprinted | Greenhouse, Ashby, Lever, SmartRecruiters |
| Single-poll-cycle job volume from one ATS | 228,000–232,000 rows (mostly already-seen) |

---

## Two engineering stories

### 1. A 13-minute poll hang, fixed to sub-second — batch-write chunking

**Symptom.** A full re-poll's write phase hung for 13+ minutes on a single `INSERT`
with zero progress. It happened three separate times, each hang tracing to a different
one of five batch functions in `db.py`, in call order.

**Diagnosis.** `pg_stat_activity` showed the stuck query's `wait_event` was
`ClientRead` — Postgres was *idle*, waiting on the client. Not a slow query; a
client-side bottleneck. The Python process was sitting at 1.3–1.4 GB RSS.

**Root cause.** Each batch function built its SQL parameters as full-length Python
lists — one list per column, `unnest()`'d in the query — over the *entire* input in a
single call. At normal poll volume this was invisible. At a full cycle's real volume —
one ATS alone returning 228K–232K jobs, nearly all already seen — building 17 parallel
Python lists plus per-row JSON/string encoding for hundreds of thousands of rows
consumed enough CPU and memory that the query never finished sending to Postgres.

**Fix.** All five functions now process input in bounded 2,000-row chunks via a shared
`_chunks()` helper. A 10,000-row `repair_metadata_batch` call that was previously part
of a call that never returned now completes in **0.84 s**.

**Follow-on.** Since no ATS exposes a delta API, a second fix added SHA-256
payload-hash change detection: hash the raw response before parsing, and if it matches
the stored hash, skip the company entirely — no parse, no diff, no write. Ashby also
sends a real `If-None-Match` header (it returns genuine HTTP 304s) and skips the
download itself. Measured cycle-over-cycle once hashes warm: **Lever −92%, Ashby −93%,
Greenhouse −92%** jobs processed.

See `decisions/0006-unbounded-batch-chunking.md`.

### 2. A Cloudflare block that looked exactly like a dead job

**Symptom.** In a 1,000-job test run, 404 of ~889 real attempts (45%) came back as
"dead listing." That number was suspiciously high for a working system, so it got
interrogated instead of accepted.

**Root cause.** The listing-freshness check assumed a live job's final URL always
contains `greenhouse.io` or `/jobs/` — true for standard Greenhouse pages and for
branded career pages that redirect through a `job-boards.greenhouse.io` embed, but
**false by design** for a company like `jobs.bayada.com` that hosts its entire apply
flow on its own domain and never redirects through greenhouse.io at all. A Cloudflare
403/429 challenge on such a domain is served at the *same* URL (no redirect happens),
so the check was silently marking every currently-blocked branded-domain job as
**permanently dead**. Confirmed live: **146 of the 404 "dead" jobs in that one run were
a single blocked domain** — almost all still-live jobs caught mid-block, not expired.

**Fix.** A 403/429 response is now treated as *inconclusive* ("assume alive"), the same
posture already used for network errors — a block is evidence of a block, not evidence
a listing is gone. The URL-shape heuristic is also skipped entirely when no redirect
happened at all, since that tells you nothing for a domain that never routes through
greenhouse.io either way.

**Repair.** A one-time pass re-verified every job previously marked inactive (536
rows) against the fixed logic: **437 were reactivated** (wrongly marked dead), 99
confirmed genuinely dead.

**Lesson.** A suspiciously large number in a "working" system is worth interrogating,
not just reporting. The evidence — a `?error=true` vs. a 403 in the request log — had
been sitting in every prior run's logs; it just hadn't been cross-referenced against
the specific failing job IDs.

---

## Repository map

| Path | Purpose |
|---|---|
| `main.py` | Orchestrator + APScheduler: polling, matching, tailoring, cleanup |
| `config.py` | All constants and env config — single source of truth |
| `db.py` | asyncpg pool and shared DB helpers (all batch writes chunked) |
| `discover_companies.py` | Common Crawl CDX crawl → company slug lists |
| `api/server.py` | FastAPI: user ingestion, job claim/lifecycle endpoints |
| `pollers/` | Per-ATS pollers + shared normalization (`seniority`, `geography`, `gh_metadata`, `metadata_categories`, `filter`) |
| `pipeline/` | `detector → enricher → scorer → injector → rewriter → formatter → matcher → tailor_worker → discovery_worker` |
| `migrations/` | 30 Postgres migrations |
| `extension/` | Manifest V3 Chrome extension — `filler_utils.js` shared filler + per-ATS content scripts |
| `corpus_analysis/` | Form-field taxonomy, interpreter, replay/parity tooling |
| `landing-page/` | Vite + React marketing site (independent of the backend) |
| `decisions/` | Architecture decision records and incident postmortems |

---

## How to run

```bash
docker compose up -d                 # Postgres
python scripts/run_migrations.py     # apply migrations

# load .env (see .env.example), then:
python main.py --no-discover         # full pipeline, skip company discovery
uvicorn api.server:app --reload      # API
python -m pipeline.matcher --all     # one matcher cycle against all jobs
```

Environment variables are documented in `.env.example`. The resume-tailoring layers
(`pipeline/rewriter.py`) require an `OPENAI_API_KEY`; without it, that layer returns
the resume unchanged and the rest of the pipeline runs normally.

---

## Tech

Python (asyncio, asyncpg, FastAPI, httpx, APScheduler) · Postgres · sentence-transformers ·
WeasyPrint · Chrome Manifest V3 · Vite + React + TypeScript (landing page)
