# Decisions index

Architecture Decision Records — one file per decision that needs to outlive
the session it was made in. Immutable once written: a later decision that
changes course adds a new ADR and marks the old one superseded, it doesn't
edit history in place. STATE.md and CLAUDE.md link here instead of
re-explaining a decision inline.

- [0001](0001-seniority-classification-rejected.md) — categorical seniority-level enum built, then rejected after real employer data showed ~50/50 ambiguity even for common titles like "Director"; replaced with literal years-of-experience regex extraction, null when unstated
- [0002](0002-intern-only-scope-removed.md) — `is_intern_role()` title-drop-gate removed from 5 of 7 pollers; Persift's real scope is every seniority level, not just interns (the gate was a leftover from an earlier narrower vision, was silently destroying ~99% of real postings)
- [0003](0003-category-classifier-design.md) — LLM category-classifier fallback design: Haiku not Opus, inline per poll cycle not a batch job, must allow empty/no-category rather than guess. Designed Jul 21, largely superseded in practice by [0006](0006-unbounded-batch-chunking.md)'s discovery that structured ATS metadata resolves far more jobs than assumed — re-sizing needed before building
- [0004](0004-target-arch-status-lifecycle.md) — the status-lifecycle rename (`queued→matched`, etc.) and single-writer-per-edge design underpinning the whole `user_jobs` state machine
- [0005](0005-corpus-harvester-no-reuse.md) — the P1.2 corpus harvester must not import/reuse `extension/filler_utils.js` — a fresh, independent extraction pass, so the corpus isn't just re-confirming the same blind spots the code it's meant to validate already has
- [0006](0006-unbounded-batch-chunking.md) — Jul 22 incident: unbounded batch DB writes (building full-cycle-sized Python lists before a single query) caused three full poll-cycle hangs; fixed via chunking + a payload-hash/ETag change-detection skip that cut reprocessing ~92% at steady state
- [0007](0007-scope-detection-not-solvable-by-metadata.md) — Jul 23 negative result: in-scope vs. out-of-scope job detection can't be solved by company name or ATS department/function metadata — checked systematically, real professional roles and real out-of-scope roles sit under identical labels/companies. Not attempted, deliberately deferred.
- [0008](0008-corpus-harvester-scale-and-scope-gap.md) — P1.2's corpus harvester (767 Greenhouse jobs, built pre-pipeline-fix) is now a stale, undersized, single-ATS foundation relative to the real 246K+-job, 4-ATS pipeline; needs rescoping to all ATSes at real volume before P1.3/P1.4 generalize. Flagged, not started.
- [0009](0009-quality-over-quantity-matching.md) — Jul 25: founder chose quality over quantity for matching, based on real precision data (Tier 1+2 92.5% exact match vs Tier 3's 21.3%-36.8%-confidently-wrong range even after improvements). No code change needed — Tier 3 was never wired into the live matcher; this converts that from an unfinished gap into a deliberate choice not to wire it in.
- [0010](0010-verification-is-mechanical-not-semantic.md) — Aug 2: P1.5's verify/retry (`isInputFilled()`) confirms a value landed in a field, not that it's the *correct* value — a misclassified field with a resolvable profile value logs `filled (verified)` identically to a correct fill. Found via the first live browser test. Acknowledged, not fixed; real fix needs read-back cross-checking, semantic re-verification, or `field_corrections` (P2.3) at scale.
