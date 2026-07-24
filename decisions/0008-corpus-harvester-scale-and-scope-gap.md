# 0008 — P1.2 corpus harvester is Greenhouse-only and pre-dates the pipeline fix that unlocked full job volume; needs rescoping before P1.3/P1.4 generalize

**Date:** 2026-07-23
**Status:** flagged, not started — future work, don't lose this
**Files:** `pipeline/corpus_harvester.py`, `corpus/README.md`, `corpus_analysis/README.md`

## Context

P1.2's corpus harvester was built and run 2026-07-17 against **767 Greenhouse
jobs** — at the time, effectively all of what the `jobs` table held, because
`is_intern_role()`'s title-drop-gate (removed 2026-07-21, see
[0002](0002-intern-only-scope-removed.md)) was silently discarding ~99% of
real postings across the board. The harvester's sample size was a reasonable
reflection of "all available data" *at that moment* — not a deliberate
scoping choice.

Since then: the intern-scope bug was fixed, discovery was widened, and the
ingestion pipeline now holds **246,333 jobs across all 4 direct-ATS pollers
plus Jobright** (see STATE.md's Jul 23 2026 entry for the full
data-completeness pass this same week). The corpus harvester's Greenhouse-
only, 767-job foundation is now a small, stale slice of what the real
pipeline produces — both in volume (767 vs. 20,837+ Greenhouse jobs alone)
and in ATS coverage (Greenhouse only, vs. Greenhouse/Ashby/Lever/
SmartRecruiters all needing real autofill support per the beta launch scope
in `CLAUDE.md`).

## Why this isn't a quick "just run it again with a higher limit"

Read `pipeline/corpus_harvester.py` in full while investigating this (Jul 23
2026, prompted by a founder question about whether one harvester could cover
all ATSes). It is not a generic "read job listings" tool — it drives a real
headless browser to each job's live `apply_url` and reads the **rendered
application form's DOM** (labels, field types, options, container HTML) for
`FORM_ENGINE_DESIGN.md`'s field-classification work. Three concrete,
ATS-specific things are hardcoded to Greenhouse:

1. `_fetch_target_jobs`'s query: `WHERE j.ats = 'greenhouse'` — literal filter,
   not just an unpopulated default.
2. `_FIND_GREENHOUSE_IFRAME_JS` — Greenhouse-specific handling for jobs
   embedded via `<iframe src="job-boards.greenhouse.io/embed/...">` on a
   company's own career site, where the top-level page is just site chrome
   and the real form lives inside the iframe.
3. The underlying premise: every ATS renders a structurally different
   application form (different framework, different embed/iframe
   conventions, different field markup conventions) — that structural
   difference is the entire reason a harvester-then-classify approach exists
   instead of hand-tuning against a few forms (see
   [0005](0005-corpus-harvester-no-reuse.md) for why hand-tuning was
   rejected in the first place).

**What likely DOES generalize across ATSes, unchanged:** `_EXTRACTION_JS`
(the exhaustive field-discovery logic — label-finding, section-heuristic,
container-HTML capture), the DOM-stability wait, and the manifest/gzip
storage format. These don't reference Greenhouse anywhere.

**What does NOT generalize and would need its own per-ATS logic:** reaching
the real form in the first place — the iframe-detection quirk is
Greenhouse-specific; Ashby/Lever/SmartRecruiters almost certainly have their
own equivalent-but-different quirks (or none) that haven't been investigated
at all yet.

## Decision

Not started. Flagging now so it isn't lost, per the founder's explicit
framing: *"if not now it's gonna be done later."* Likely shape when picked
up: one shared extraction engine (reusing `_EXTRACTION_JS`'s field-discovery
logic and storage format) + a thin per-ATS front-end that knows how to reach
that ATS's real rendered form, re-run at the real current job volume across
all 4 ATSes, not just a Greenhouse-only re-run at higher `--limit`.

## Explicitly a different problem from the Jul 23 category-classification eval corpus

Don't conflate this with the ~1,000-job stratified sample being built to
evaluate the category-classification 3-tier pipeline (metadata → regex →
LLM fallback) — that corpus reads job **description text** via each ATS's
existing API (no browser, no forms) to label the *job category*. This
decision is about harvesting live **application forms** to extract *form
fields* for autofill. Same word ("corpus"/"harvester"), same underlying
"read real examples before building the classifier" discipline, completely
different data, completely different purpose, completely different code
path.
