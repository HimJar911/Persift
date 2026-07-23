# 0006 — Unbounded batch DB writes caused multi-hour poll hangs; fixed via chunking + payload-hash skip

**Date:** 2026-07-22
**Status:** accepted, live, verified against a real full poll cycle
**Files:** `db.py`, `pollers/greenhouse.py`, `ashby.py`, `lever.py`,
`smartrecruiters.py`, `main.py`, migration 024

## Context

While sizing the category-LLM-classifier work ([0003](0003-category-classifier-design.md)),
a full re-poll was run to land two capture-gap fixes (Greenhouse `departments`
field, Lever `department` field — see "capture fixes" below). The poll's
write phase hung for 13+ minutes on a single INSERT with zero progress.

## Root cause

`db.py`'s batch functions (`mark_seen_batch`, `repair_jobs_batch`,
`repair_metadata_batch`, `find_incomplete_ids`, `filter_new_ids`) each built
their SQL parameters as full-length Python lists (one list per column,
`unnest()`'d in the query) over the **entire** input in one call. At normal
poll volume this was invisible. At a full-cycle's real volume — one ATS
alone returned 228K-232K jobs in a single cycle, nearly all already-seen —
building 17 parallel Python lists plus per-row JSON/string encoding for
hundreds of thousands of rows consumed enough CPU/memory that the query
never finished sending to Postgres.

**Confirmed via `pg_stat_activity`**: the stuck query's `wait_event` was
`ClientRead` — Postgres was idle, waiting on the client. Not a slow query;
a client-side bottleneck. Python process memory hit 1.3-1.4GB during the
hang.

This happened on 3 separate attempts before being fully resolved — each
attempt's stuck point traced to a different one of the 5 functions above, in
call order (`filter_new_ids` runs first in `detect_new_jobs`, so it has the
largest unfiltered input of the whole path and was the last gap found).

## Fix 1 — chunked batch writes

All 5 functions in `db.py` now process input in bounded chunks
(`_BATCH_CHUNK_SIZE = 2000`) via a shared `_chunks()` helper, looping the
same per-chunk query instead of one call over the full list. Verified: a
10,000-row `repair_metadata_batch` call completed in 0.84s (previously would
have been part of a call that never returned).

## Fix 2 — payload-hash / ETag change-detection skip

None of Greenhouse/Ashby/Lever/SmartRecruiters expose a delta/since API —
every poll re-fetches a company's entire current listing. Most companies'
listings don't change between two 10-minute polls, so re-parsing and
re-diffing the full response every cycle was pure waste on top of the
crash risk.

`companies.last_payload_hash` / `last_response_etag` (migration 024): each
poller hashes the raw response body (SHA-256) before parsing; if it matches
the stored hash, the company is skipped entirely — no parse, no DB diff, no
write. Ashby additionally sends a real `If-None-Match` header (confirmed
live: Ashby returns genuine HTTP 304s) and skips the download itself, not
just post-download processing. New `company_poll_log` outcome,
`ok_unchanged`, distinct from `ok_zero_jobs` so the dead-company signal that
table exists for doesn't get corrupted by conflating "nothing changed" with
"nothing posted."

**Verified impact at real scale** (cycle-over-cycle, once hashes warm):
Lever -92% jobs processed, Ashby -93%, Greenhouse -92%. SmartRecruiters'
skip only applies to single-page companies (~100 jobs or fewer) — multi-page
companies still get fully re-fetched and parsed each cycle, a known,
accepted gap (smaller win there, correctness prioritized over optimizing the
rarer large-employer case under incident pressure).

## Fix 3 — `log_company_poll` wired into all 4 in-scope pollers

Previously only `greenhouse.py` called `log_company_poll` (migration 021
existed specifically to answer "why are so many companies contributing
nothing," but only had Greenhouse data). Now Ashby, Lever, and
SmartRecruiters log every poll attempt too, mirroring Greenhouse's exact
outcome-classification pattern. This gives permanent, always-on
dead-company/concentration visibility across all 4 ATSes going forward —
already surfaced real findings (Lever: 43% of polled companies return 404,
by far the worst of any ATS; Greenhouse: ~30% zero-or-404 in one cycle).

## Fix 4 — Slack notification removed from the polling path

`main.py`'s `process_single_job` fired a live Slack webhook call for every
newly-detected job, concurrently, via `asyncio.gather`. This predates the
current matcher→tailor_worker→extension design (a placeholder from before
the extension existed) but was still live. At real new-job volume (tens of
thousands after the chunking fix let large batches through), this produced
thousands of concurrent HTTP calls competing with `detect_new_jobs`'s own DB
writes for event-loop scheduling time — measured via timing gaps between
ATSes' `detect_new_jobs` completion (Ashby: clean ~6min; Greenhouse, running
after Ashby/Workday's notification load had piled up: ~23min for a similar
job count) and via Slack's own webhook rate-limiting (8,600+ failed sends in
one run).

**Decision: removed entirely**, not throttled. `process_new_jobs` and
`run_jobright_cycle` now just log new jobs (`_log_new_job`) instead of
notifying. Real per-user job delivery is the extension claiming from
`user_jobs`, not this path — notification-on-new-job, if wanted again,
should be rebuilt against the extension's actual design, not this dead
placeholder.

## Verified end state

Fourth full poll cycle attempt (first three failed/were killed) completed
cleanly: `=== Pipeline run complete ===`, exit code 0, zero errors, 246,333
total jobs in the DB (up from a 22,682 baseline at the start of the
session). `company_poll_log` showed thousands of real `ok_unchanged` skips
per ATS, confirming fix 2 compounds correctly across repeated cycles.

## Real capture-gap fixes landed the same session (the original trigger)

Two real, narrower bugs found and fixed while investigating category
classification, unrelated to the hang above but landed in the same session:
- **Greenhouse**: `job.get("departments")` was never captured (only the
  near-always-null `metadata` field was) — `departments` is a real,
  sometimes-populated employer-declared category field. Now captured
  alongside `metadata` in `raw_ats_metadata`.
- **Lever**: only `categories.team` was captured, not `categories.department`
  — `department` is the more useful, coarser-grained field (`team` is
  frequently a company-internal codename, e.g. Palantir's "Delta"/"Echo").
  Now captured alongside `team`.
- **`db.repair_metadata_batch`** (new function): backfills `raw_ats_metadata`
  on existing rows whose value is still `NULL`/`{}`, wired into
  `detect_new_jobs`'s self-healing repair pass — so these two capture fixes
  (and any future ones) reach already-inserted rows without a separate
  one-time script, consistent with `[[feedback_seamless_integration]]`.

**Not yet done**: turning this newly-captured metadata into actual category
assignments (SmartRecruiters `function` especially — confirmed a real,
fairly stable enum, though wider sampling found 32 distinct values not the
initial 18 seen in one sample — don't treat any sample as exhaustive without
checking against the live API first). See STATE.md's current RESUME HERE.
