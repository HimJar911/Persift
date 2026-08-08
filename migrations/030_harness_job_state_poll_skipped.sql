-- migrations/030_harness_job_state_poll_skipped.sql
-- Adds 'poll_skipped' to harness_job_state.outcome's CHECK constraint.
--
-- Companion to migration 029's no_job_available: that migration's
-- last_poll_result field turned out not to fix the underlying bug it was
-- built for (see STATE.md "THE OPEN MYSTERY" and the extension/background.js
-- rewrite the same day) — a single shared, last-write-wins storage slot,
-- discovered via harness-side polling, could still be overwritten by a
-- LATER poll-cycle invocation (the recurring poll_alarm, in particular)
-- before the harness's own polling loop ever read the value it was waiting
-- for. Confirmed live: it never fired once across 40+ real dead-job catches
-- in real multi-worker harness runs, despite working in every isolated test.
--
-- Real fix: test_pipeline/job_driver.py's _trigger_poll() now calls a new
-- harness-facing entry point (extension/background.js's
-- runPollCycleForHarness()) that returns its result DIRECTLY via
-- sw.evaluate()'s own return value — no storage round-trip, so no window
-- for another invocation to overwrite it. That direct result can be
-- 'no_job' (existing no_job_available outcome, unchanged meaning) or one of
-- 3 skipped_* results from a re-entrancy guard added at the same time
-- (skipped_busy: an alarm-driven cycle was already in flight;
-- skipped_stale_reset / skipped_not_idle: two early-return guards inside
-- the poll cycle — both should be practically unreachable on the harness's
-- own call since _reset_extension_state() always sets phase='idle'
-- immediately before triggering, but handled defensively since "should be
-- unreachable" isn't the same guarantee as "is unreachable").
--
-- All 3 skipped_* results collapse to one new outcome, 'poll_skipped', with
-- the specific reason preserved in failure_reason — a real, honestly-named,
-- rare timing condition, not absorbed into no_job_available (nothing was
-- actually claimed here) and not left to fall through to a generic timeout
-- (nothing is broken; the poll cycle just legitimately couldn't run yet).

ALTER TABLE harness_job_state DROP CONSTRAINT IF EXISTS harness_job_state_outcome_check;

ALTER TABLE harness_job_state ADD CONSTRAINT harness_job_state_outcome_check CHECK (
    outcome IN (
        'pending', 'claimed', 'mechanically_verified', 'needs_review_non_submit',
        'failed', 'timeout', 'harness_error', 'skipped_blocked', 'no_job_available',
        'poll_skipped'
    )
);
