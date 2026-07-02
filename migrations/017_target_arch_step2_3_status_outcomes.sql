-- Migration 017 — Target Architecture, Steps 2+3: status rename, outcome cleanup, constraints.
-- Atomic: widen status CHECK -> rewrite rows -> delete fake outcomes -> narrow CHECK
--          -> reconcile submission_mode -> add source->type coupling CHECK.
-- All-or-nothing. See DESIGN_NOTES.md Migration path steps 2, 3.
--
-- Ground truth (July 1, 2026): 4 user_jobs all 'needs_review'; 51 outcomes ALL
-- extension_detected/rejected (bug #3 garbage — 0 gmail signals, 0 correction
-- chains, 1 job). 'dismissed' is not a live status (popup 'dismiss' = clear_review
-- UI only); it is dropped from the new set (user dismiss = skip -> abandoned).

BEGIN;

-- === Step 2: WIDEN status CHECK (allow old + new transiently) ===
ALTER TABLE user_jobs DROP CONSTRAINT user_jobs_status_check;
ALTER TABLE user_jobs ADD CONSTRAINT user_jobs_status_check CHECK (status IN (
    -- old
    'queued','applying','applied','failed','failed_stale','expired','needs_review','dismissed','notify_only',
    -- new
    'matched','preparing','ready','submitting','awaiting_review','submitted','abandoned'
));

-- === Step 3a: rewrite rows to new lifecycle names ===
-- Only needs_review rows exist today; the rest are defined for completeness (0 rows).
UPDATE user_jobs SET status = 'awaiting_review', updated_at = NOW() WHERE status = 'needs_review';
UPDATE user_jobs SET status = 'matched'         WHERE status = 'queued';
UPDATE user_jobs SET status = 'ready'           WHERE status = 'applying';
UPDATE user_jobs SET status = 'submitted'       WHERE status = 'applied';
UPDATE user_jobs SET status = 'abandoned'       WHERE status IN ('failed','failed_stale','expired','dismissed');

-- === Step 3b: DELETE the 51 fake extension_detected/rejected outcomes (bug #3) ===
-- extension_detected may ONLY ever write applied_confirmed (source->type rule).
-- Every rejected row from this source is illegitimate. Verified: no signals/chains.
DELETE FROM application_outcomes
WHERE outcome_source = 'extension_detected' AND outcome_type <> 'applied_confirmed';

-- === Step 4: NARROW status CHECK to new names only ===
ALTER TABLE user_jobs DROP CONSTRAINT user_jobs_status_check;
ALTER TABLE user_jobs ADD CONSTRAINT user_jobs_status_check CHECK (status IN (
    'matched','preparing','ready','submitting','awaiting_review','submitted','abandoned'
));

-- === Step 5: reconcile submission_mode -> auto | review (notify_only CUT) ===
ALTER TABLE user_jobs DROP CONSTRAINT user_jobs_submission_mode_check;
ALTER TABLE user_jobs ADD CONSTRAINT user_jobs_submission_mode_check
    CHECK (submission_mode IS NULL OR submission_mode IN ('auto','review'));

-- === Step 6: source->type coupling CHECK (bug #3 teeth) — safe now the 51 rows are gone ===
-- extension_detected may ONLY write applied_confirmed. Employer verdicts come only
-- from gmail_auto / manual.
ALTER TABLE application_outcomes ADD CONSTRAINT application_outcomes_source_type_check
    CHECK (outcome_source <> 'extension_detected' OR outcome_type = 'applied_confirmed');

COMMIT;
