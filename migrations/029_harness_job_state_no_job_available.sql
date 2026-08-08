-- migrations/029_harness_job_state_no_job_available.sql
-- Adds 'no_job_available' to harness_job_state.outcome's CHECK constraint.
--
-- Real bug found live (Aug 8 2026, STATE.md's timeout investigation, after
-- the jobs.is_active freshness check landed): job_driver.py's
-- _poll_for_terminal() infers what happened from a live phase transition in
-- chrome.storage.local (idle -> fetching -> idle), polled on a 1.5s
-- interval. background.js's runPollCycle() can complete that whole
-- idle->fetching->idle round-trip (a claim that correctly finds nothing to
-- do, e.g. every 'ready' row was a job the freshness check just abandoned)
-- in well under a second -- faster than the harness's own poll interval --
-- so the harness can miss the transition entirely and burn the full 90s
-- timeout on an outcome that was actually correct and fast. Confirmed live:
-- every single re-tested dead-listing job showed this exact ~110s pattern
-- even in complete isolation (single worker, zero concurrency), while a
-- direct /jobs/claim call against the identical job resolved in ~200ms.
--
-- Fixed by having runPollCycle() write a durable last_poll_result field
-- (not a live-only transition) whenever a claim resolves to no job, and
-- having _poll_for_terminal check that field in addition to the phase
-- transition -- durable state can't be missed by a polling race the way a
-- transient phase flicker can.
--
-- 'no_job_available' is deliberately its own outcome, not folded into
-- 'timeout' (nothing broke) or 'mechanically_verified' (no form was
-- filled) -- see STATE.md for the full reasoning. It keeps the freshness
-- check's real, measurable impact visible instead of hiding it inside a
-- bucket that means something else.

ALTER TABLE harness_job_state DROP CONSTRAINT IF EXISTS harness_job_state_outcome_check;

ALTER TABLE harness_job_state ADD CONSTRAINT harness_job_state_outcome_check CHECK (
    outcome IN (
        'pending', 'claimed', 'mechanically_verified', 'needs_review_non_submit',
        'failed', 'timeout', 'harness_error', 'skipped_blocked', 'no_job_available'
    )
);
