# `category_eval/` + `category_eval_v2/` — category-classification eval corpus (side mission)

**Not the same thing as `corpus_analysis/`'s other contents.** That directory
(`oc_compact_full.json`, `cluster_decisions.json`, etc.) is P1.2/P1.3's form-field
corpus — reads live rendered application *forms* to extract *form fields* for
autofill. This directory reads job *description text* via each ATS's existing
API (no browser) to label the job's *category* (Software Engineering, Sales,
etc.). Same "read real examples before building the classifier" discipline,
completely different data and purpose. See `decisions/0008` for the explicit
prior confusion about this.

**Contents are gitignored — this README is the only tracked file.** Everything
else here (batch files, per-batch label files, merged/frozen corpora) is
regenerable: the raw source is `jobs` table rows in Postgres, the labels come
from dispatched Haiku subagents. Regenerating exactly reproduces the process
below, though not byte-identical output (random sampling, LLM non-determinism).

## Why this exists

`pollers/filter.py`'s `assign_categories()` (Tier 1: ATS metadata, Tier 2:
title-first regex) leaves some jobs uncategorized or wrong. Before building
Tier 3 (an LLM fallback, `decisions/0003`), we needed a real, independently-
labeled eval corpus to measure it against — otherwise there's no way to tell
"the pipeline resolves more jobs now" from "the pipeline resolves more jobs
*correctly* now" (STATE.md's Jul 23 finding: empty-category-rate improving
said nothing about correctness).

## What was built

**v1 (`category_eval/`):** 1,150 jobs — 750 "unresolved" (Tier 1+2 both fail,
a near-full census of the real 1,529-job unresolved pool at the time), 250
"resolved_control" (Tier 1+2 claim an answer — checks if the pipeline's
existing confidence is trustworthy), 150 Greenhouse (kept separate — no
verified country signal, see `decisions/0007`). Each job independently labeled
by a Haiku subagent against the 23-category taxonomy in `pollers/filter.py`,
allowed to abstain. Tier 3 (a Haiku-subagent stand-in for the real LLM call —
see below) then ran against the 750 unresolved jobs and was scored against
the independent labels.

**v2 (`category_eval_v2/`):** scaled up to test whether v1's numbers were
real or small-sample noise. 5,000 jobs sampled: the *entire* real unresolved
pool (1,529 jobs — grew slightly since v1 as new jobs were polled) + 3,471
resolved-control. Ground-truth labeling was stopped partway (1,500 of 5,000
labeled — all of it happened to land inside the unresolved block) due to a
usage-budget checkpoint mid-session. Tier 3 was then run to completion against
the full 1,495-job labeled-and-matched unresolved pool.

## Key findings (Jul 24 2026 session)

- **v1 Tier 3 result (750 jobs):** 53.9% exact match, 78.0% any-overlap,
  15.8% confidently-wrong, 6.2% false-negative (abstained when it shouldn't).
- **v2 full-pool result (1,495 jobs, the real number — see below):** 36.8%
  exact match, 69.5% any-overlap, 21.3% confidently-wrong, 9.2% false-negative.
  **These numbers moved substantially from smaller samples** (a 900-job partial
  read showed 54.7%/77.5%/19.9%/2.6%) — confirms the 750-job v1 sample and the
  900-job partial were both still noisy; don't trust either as final.
- **Two real Tier 3 output defects found and normalized before scoring:** a
  `health_care` vs `"health care"` taxonomy-key typo (a few jobs), and one
  invented out-of-taxonomy category (`procurement`, should have been
  `supply_chain`) — both point at the same gap `decisions/0003` already
  flagged: Tier 3 needs schema-constrained structured output in production,
  not free-text category generation.
- **Confidently-wrong error clusters, real examples read by hand:** (1)
  "Engineer"-titled hardware-adjacent-but-actually-software roles (Controls
  Engineer, DSP Engineer, Network Engineer) misrouted to
  `engineering_and_development` instead of `software_engineering`; (2)
  `consulting` (Solutions Architect/Solution Engineer/Deployment Strategist —
  external customer-facing technical work) getting scattered into
  `business_analyst`/`product_management`/`software_engineering` instead;
  (3) genuine `supply_chain` vs `engineering_and_development`/
  `project_management` ambiguity in manufacturing-ops roles. The v2 labeling
  prompt added explicit clarifications for these three; whether that actually
  moved Tier 3's error rate down was not re-tested (Tier 3's prompt was not
  updated with the same clarifications — worth doing before trusting the
  gap is closed).
- **The v1 "resolved_control" 250-job sample had a real sampling bug**
  (caught and fixed): the quick title-only+metadata check used to select
  "resolved" jobs disagreed with what the actual `assign_categories()`
  function produces (173 of 250 were actually empty). Once corrected to the
  77 jobs that genuinely resolve, Tier 1+2 precision is strong: 92.2% exact
  match, 96.1% any-overlap, 1.3% abstain. **This 77-job number is still the
  only resolved-control data point** — v2's much larger 3,471-job
  resolved-control sample was never labeled (stopped before reaching that
  block of the corpus).

## Mechanism: Haiku subagents standing in for the real Tier 3 LLM call

No `ANTHROPIC_API_KEY` is wired into `pollers/llm_classifier.py` yet — this
was a one-time architecture test, not a live-scheduled poller, so "Tier 3's
classify call" was simulated by dispatching Haiku subagents (via the Agent
tool) instead of a real API call. `pollers/llm_classifier.py`'s
`classify_batch(jobs, classify_fn)` takes a pluggable `classify_fn` for
exactly this reason — production wiring is a real API call; this session's
`classify_fn` was "dispatch N subagents, merge their JSON output."

**Cost lesson learned mid-session:** batch size was 30 jobs/subagent-call for
most of this work. A same-model cost comparison at 60/100/150 jobs-per-call
found no quality loss at any size tested, and per-job token cost dropped
substantially at 100+ (roughly 2x cheaper per job than 30). If regenerating
this corpus, use 100 jobs/batch, not 30 — no known downside found, and it
cuts total subagent dispatches roughly 3x. (One observed anomaly: a 100-job
probe batch returned records in dis-order once — job_ids were all correct
and complete, just resequenced. Harmless if merging by `job_id` — as this
process does — but worth knowing about if a future run assumes input/output
order match.)

## Regenerating or resuming

1. Sample from `jobs` (see the exact queries and stratification logic —
   confirmed-US subset via
   `WHERE ats IN ('smartrecruiters','lever','ashby') AND raw_ats_metadata->>'country'='US'`,
   Greenhouse has no country field, unresolved = neither
   `assign_categories(title, '')` nor `raw_ats_metadata`'s category/function/
   department fields produce an answer).
2. Split into batches (100/batch recommended, not 30).
3. Dispatch Haiku subagents per batch with the labeling prompt. **The exact
   verbatim prompt now lives in `STATE.md`'s RESUME HERE section ("Labeling
   prompt" subsection) — use that, not this file.** (Jul 24's version of
   this README pointed to "git log / session transcript" for the prompt
   text; that turned out to be a dead end — it wasn't actually recoverable
   and had to be re-supplied from scratch Jul 25. Don't repeat that mistake
   — if you use the prompt, also copy it somewhere durable like this file
   or STATE.md, don't just point at chat history again.)
4. Merge by `job_id` (not position) into a frozen corpus.
5. Run the same dispatch pattern with the Tier 3 framing (production-style
   prompt: no confidence/note fields, empty-list-is-correct emphasized) to
   get predictions, merge, score.

**Status as of Jul 25 2026 (see STATE.md RESUME HERE for full detail):**
- The unresolved pool (1,495 jobs) was fully labeled Jul 24
  (`frozen_eval_corpus_v2_partial.jsonl` + `gt_labels/gt_batch_NNN_labels.jsonl`,
  30/batch).
- The 3,471-job resolved-control block was already split into 35 batches of
  100 (`category_eval_v2/gt_batches_b100/gt100_batch_00.jsonl`–`_34.jsonl`)
  — confirmed via a bucket audit (3,471 `resolved_control_v2` + 29 stray
  `unresolved_v2` rows), no regeneration needed despite what this doc
  previously implied.
- **25 of 35 resolved-control batches labeled** as of Jul 25
  (`gt_labels/gt100_batch_00_labels.jsonl`–`_24_labels.jsonl`). 10 remain
  (`_25`–`_34`). Check `gt_labels/` for which exist before dispatching more.
- Once all 35 are labeled: merge by `job_id`, compute Tier 1+2 precision/
  recall against the full resolved-control block (same method as the 77-job
  v1 clean sample), excluding jobs where `current_tier12_categories` is
  empty despite being in the resolved bucket (recheck for the v1 sampling
  bug here too).

**Not yet done after that (explicitly deferred to the founder, not solo
decisions):**
- Re-test Tier 3 with the category-clarifications prompt update (only the
  *ground-truth labeling* prompt got the clarifications; Tier 3 itself
  didn't, so the three error clusters found may still be present at the
  same rate — unconfirmed either way).
- Add the schema-constrained structured-output layer `decisions/0003`
  already calls for, then re-score against this same frozen corpus to see
  if it closes the `procurement`-style invented-category gap.
