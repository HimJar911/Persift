# 0004 — Target-architecture status-lifecycle rename

**Date:** 2026-07-01
**Status:** accepted, live, fully migrated across the entire stack
**Files:** migrations 015-018, `api/server.py`, `pipeline/matcher.py`,
`pipeline/tailor_worker.py`, `main.py` cleanup job, `extension/*`

## Decision

Clean-break migration to a new `user_jobs` status lifecycle and single-
writer-per-edge model, from `DESIGN_NOTES.md`'s completed design:

- **Status rename**: `queued→matched`, `applying→ready/submitting`,
  `applied→submitted`, `needs_review→awaiting_review`,
  `failed/failed_stale/expired/dismissed→abandoned` (migration 017).
- **Field homes fixed** (migration 016): profile facts moved from
  `application_settings` JSONB to columns — one home per fact, governing
  rule in CLAUDE.md's "Profile fields" section.
- **`notified` terminal status added** (migration 018) — excluded-company
  matches: notify, never apply. A genuine terminal phase, distinct from the
  cut `notify_only` submission mode.
- **Deleted 51 fake `extension_detected`/`rejected` outcomes** that existed
  from a bug where source/type conflation made fake outcomes structurally
  possible — the migration made this bug structurally impossible going
  forward (source→type CHECK constraint).

Full lifecycle diagram and single-writer-per-edge invariant: see
`ARCHITECTURE.md`. This is foundational — nearly everything downstream
(matcher, tailor_worker, extension, API) reads/writes this status field, so
changing it again would have the same wide blast radius as the original
migration.
