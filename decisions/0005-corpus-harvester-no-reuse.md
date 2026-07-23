# 0005 — Corpus harvester must not reuse `filler_utils.js`

**Date:** 2026-07-05 (design), built 2026-07-17
**Status:** accepted, live
**Files:** `pipeline/corpus_harvester.py`, `corpus/README.md` (data account)

## Context

An earlier debug session on P1.1's `section` heuristic started drifting into
hand-tuning against individual postings (ACLU, then Samsung) — caught
mid-session as the form-by-form-optimization anti-pattern
`FORM_ENGINE_DESIGN.md` §1's standing rule forbids
(see `[[feedback_no_single_form_tuning]]` memory).

Founder's reframing: *"shouldn't the sandbox be built with fresh eyes from a
real corpus first, then autofill built around THAT — otherwise aren't we
defaulting to the same trial-and-error we're trying to escape."*

## Decision

The corpus harvester's in-page extraction JS is new, independently-written
code — does NOT call or import anything from `extension/filler_utils.js`.
Same for the apply-click heuristic and DOM-stability wait. If the harvester
reused the code it exists to validate, it would just re-confirm whatever
blind spots that code already has, not surface new ones.

This produced `FORM_ENGINE_DESIGN.md` §3.6a's full harvester spec. Full
build/run detail and results: `corpus/README.md` and
`corpus_analysis/README.md`.
