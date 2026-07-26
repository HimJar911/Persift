# 0009 — Matching uses only confident (Tier 1+2) categories; Tier 3 stays out of the live pipeline for now

**Date:** 2026-07-25
**Status:** accepted
**Files:** `pipeline/matcher.py`, `pollers/filter.py`, `pollers/llm_classifier.py`

## Context

With real precision numbers in hand for both tiers (see STATE.md, Jul 24-25
sessions; `corpus_analysis/category_eval/README.md`), the founder was asked
to choose between two matching strategies:

- **Quality:** only match users to jobs where category classification is
  confident. Fewer relevant jobs surfaced, but a job shown as "matched" is
  almost always a real match.
- **Quantity:** also match on Tier 3 (LLM) classifications, surfacing jobs
  Tier 1+2's regex/metadata couldn't resolve. More relevant jobs surfaced,
  but a real, measured share of "matches" are actually wrong.

## The data that decided it

- **Tier 1+2, when it produces a category at all:** 92.5% exact match,
  97.4% any-overlap, only 1.7% confidently-wrong — confirmed at real scale
  (967 scoreable jobs, v2 resolved-control block).
- **Tier 3, on jobs Tier 1+2 couldn't resolve:** 36.8% exact match, 69.5%
  any-overlap, but **21.3% confidently-wrong** — confirmed on the full
  1,495-job unresolved pool (smaller samples had given optimistic reads
  that didn't hold up at scale).
- **Re-tested Tier 3 with improved category clarifications** (same
  session) against the 53 known-hardest confusion cases: improved to 28.3%
  exact / 49.1% overlap, but **still 50.9% confidently-wrong** even with
  the fix. The improvement was real but partial, concentrated in one
  confusion cluster (hardware-vs-software titles) and barely moved another
  (supply_chain vs engineering/project_management).

A 1-in-5 (Tier 3 as-is) to roughly 1-in-2 (even the hardest known cases,
post-fix) chance of a confidently-wrong category is not a rate the founder
was willing to surface to users as a "match."

## Decision

**Founder's call: quality over quantity.** Matching stays exactly as it
already is — `pipeline/matcher.py`'s hard filter #1 reads `jobs.categories`
directly (populated only by `pollers/filter.py`'s `assign_categories()`,
i.e. Tier 1+2). **No code change was needed to implement this decision** —
Tier 3 (`pollers/llm_classifier.py`) was never wired into `main.py` or any
poller's live cycle; it only exists as a standalone module exercised by the
one-off eval corpus work (`classify_fn` was a dispatched-subagent stand-in,
no real `ANTHROPIC_API_KEY` wired in). The system already only matches on
confident categories.

**What this decision actually does:** it converts "Tier 3 isn't wired in
yet" from an unfinished-integration gap into a deliberate choice not to
wire it in, given what the data showed. This matters for future sessions —
don't treat Tier 3's disconnection from the matcher as a TODO to casually
close by calling `classify_batch()` from a poller. That would silently flip
the product to the quantity strategy without a fresh decision to do so.

## Consequence — the real tradeoff, sized

Roughly a third of jobs get no category at all from Tier 1+2 (the
1,495-of-~4,966-sampled "unresolved" rate seen in the eval work). Those
jobs are currently **invisible to matching** — a real user with a genuinely
relevant unresolved-category job will not be matched to it. This is the
accepted cost of the quality choice, not an oversight.

## Reopening this decision

If quantity is revisited later, it needs: (1) Tier 3 wired into a real poll
cycle with a real API key, not the subagent stand-in; (2) the
schema-constrained-output validation in `pollers/llm_classifier.py`
(shipped Jul 25) carried forward as a floor, not a substitute for the
accuracy work; (3) probably a different confidence-tiered UX (e.g. "matched"
vs. "possible match" shown differently) rather than treating Tier 3 output
identically to Tier 1+2 output — raised as a product idea during this
session's discussion, not decided here.
