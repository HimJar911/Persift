-- migrations/019_matcher_watermark.sql
-- P0.5 (fable_audit Area 4): replace the matcher's rolling 6-minute wall-clock
-- lookback with a durable per-job marker. The old design
-- (first_seen_at > NOW() - INTERVAL '6 minutes') silently and permanently
-- dropped any job whose insert fell outside the trailing window of whichever
-- cycle actually ran — near-certain at beta scale once cycle time can exceed
-- the 6-minute cadence. NULL = never checked by the matcher; a cycle marks
-- every job it considers (matched, notified, below-threshold, or hard-filtered
-- out for all users) so a skipped/crashed cycle just leaves rows unmarked for
-- the next cycle to pick up — no cursor to advance, nothing to get wrong.

ALTER TABLE jobs ADD COLUMN matcher_checked_at TIMESTAMPTZ;

-- Partial index: only rows never yet checked. Stays small at steady state
-- (shrinks as jobs get marked) instead of growing with the whole table.
CREATE INDEX idx_jobs_matcher_unchecked ON jobs (job_id, ats)
    WHERE matcher_checked_at IS NULL;
