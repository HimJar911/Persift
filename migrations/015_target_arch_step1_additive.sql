-- Migration 015 — Target Architecture, Step 1: additive schema only.
-- Safe: adds new column + new table. Reads nothing, rewrites no data.
-- The source->type coupling CHECK on application_outcomes is DEFERRED to step 3
-- (after the 51 fake extension_detected/rejected rows are deleted — they would
-- violate it). See DESIGN_NOTES.md Migration path.

BEGIN;

-- 1. Lease column for the atomic-claim / heartbeat mechanism (lifecycle Mechanism 1+2).
--    Only genuinely-new column; failure_reason/submission_mode/current_stage/
--    current_stage_entered_at/latest_outcome_id/retry_count already exist.
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;

-- 2. field_corrections — dedicated home for the two-snapshot diff (A/B-only PII isolation).
--    One row per review: both raw snapshots + server-derived diff.
CREATE TABLE IF NOT EXISTS field_corrections (
    id                  SERIAL PRIMARY KEY,
    user_job_id         INTEGER NOT NULL REFERENCES user_jobs(id) ON DELETE CASCADE,
    snapshot_filled     JSONB   NOT NULL,   -- #1: what Persift filled
    snapshot_submitted  JSONB   NOT NULL,   -- #2: what the user submitted
    diff                JSONB,              -- server-computed {category+label -> {before, after}}
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_field_corrections_user_job
    ON field_corrections (user_job_id);

COMMIT;
