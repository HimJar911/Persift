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
