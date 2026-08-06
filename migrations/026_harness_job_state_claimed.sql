-- migrations/026_harness_job_state_claimed.sql
-- Adds 'claimed' to harness_job_state.outcome's CHECK constraint.
--
-- Real bug found while sanity-testing test_pipeline/db_state.py against a
-- fresh local DB: claim_next_pending() set worker_id/started_at on a row but
-- left outcome='pending', so get_pending_count() (which filters on
-- outcome='pending') still counted an in-flight job as pending — a second
-- worker's claim query would see the same false-pending count, and
-- checkpoint-threshold/completion-criteria reads relying on pending vs.
-- terminal counts would be wrong during any window with in-flight jobs.
--
-- 'claimed' is not itself a terminal outcome (job_driver.py must still write
-- one of the real terminal outcomes when the job finishes) — it just marks
-- "a worker has this row, don't hand it to anyone else, don't count it as
-- untouched."

ALTER TABLE harness_job_state DROP CONSTRAINT IF EXISTS harness_job_state_outcome_check;

ALTER TABLE harness_job_state ADD CONSTRAINT harness_job_state_outcome_check CHECK (
    outcome IN (
        'pending', 'claimed', 'mechanically_verified', 'needs_review_non_submit',
        'failed', 'timeout', 'harness_error', 'skipped_blocked'
    )
);
