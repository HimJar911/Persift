# 0003 — Category LLM classifier fallback: design locked, not yet built

**Date:** 2026-07-21 (design); revisit before building — see status note
**Status:** design locked, superseded in practice — see below
**Files:** `pollers/filter.py` (`assign_categories`, `_CATEGORY_PATTERNS`)

## Status note (2026-07-22)

This ADR captures the Jul 21 design. **Before building it, re-read
[0006](0006-unbounded-batch-chunking.md) and STATE.md's current RESUME HERE**
— a Jul 22 audit found real, employer-declared category metadata
(SmartRecruiters `function`, Ashby `department`, Lever `department`,
Greenhouse `departments`) sitting captured but unused, which will resolve a
meaningful share of what this design assumed needed an LLM call. The
cost/volume sizing below is stale; don't build against it without
re-measuring after the metadata-mapping work lands.

## Context (as of Jul 21)

Title-only regex (`assign_categories`, tier 1) resolves ~66% of jobs. The
other ~34% get empty `categories` — 8,100 of 22,682 real jobs at the time.
Full-description regex as a fallback was tested and is **actively harmful**
— false-positives on benefits/legal boilerplate (a "Mobile Engineer,
Android" posting got tagged `accounting_and_finance`/`health_care`/
`human_resources`/`sales` from perks-section keyword collisions; this
pattern recurred and got worse Jul 22, see STATE.md). Section-based
boilerplate stripping was tested and disproven — 0% of sampled Greenhouse
jobs have real heading tags.

## Decisions locked in (still valid, re-verify cost sizing before building)

- **Model: `claude-haiku-4-5`, not Opus.** Bounded classification over a
  fixed ~23-category taxonomy is exactly Haiku's use case; 5x cheaper than
  Opus at this volume. Live-tested against 55 real stratified jobs —
  category classification was strong, correctly handled company-coined
  titles regex can't match, correctly avoided every false-positive trap.
- **Must return empty/no-category rather than forced to guess** — same
  "honest null beats confident wrong" rule as [0001](0001-seniority-classification-rejected.md).
- **Title-hash caching is necessary, not optional** at real poll volume —
  distinct titles repeat massively across postings and re-polls.
- **Execution model: inline within the same poll cycle**, not a separate
  scheduled batch job. Founder's framing: *"any changes we make should
  seamlessly fit in with the rest of the product"* — see
  `[[feedback_seamless_integration]]` memory. Flow: poller fetches → regex
  runs inline → regex-empty jobs queued in-memory → after the batch fetch
  completes, queued jobs classified concurrently via Haiku (Semaphore-bounded)
  → results merge back into the existing single `mark_seen_batch()` call.

## Edge cases identified, unresolved

- Existing empty-category backlog is NOT reachable by the inline design —
  `mark_seen_batch` is `ON CONFLICT DO NOTHING`, so already-inserted rows
  never get touched by a future poll. Needs its own one-time catch-up script.
- Haiku call failure/timeout mid-batch needs a defined fallback (leave
  `categories = []`, don't block the poller run) and rate-limit-aware
  concurrency.
- No correction path once a job is inserted with LLM-derived categories —
  `ON CONFLICT DO NOTHING` means never reclassified later. Open product
  question, not decided.
- Structured-output schema not yet written — should constrain to the fixed
  taxonomy so the model can't return an out-of-taxonomy category.
