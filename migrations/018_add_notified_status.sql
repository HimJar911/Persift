-- Migration 018 — add `notified` terminal lifecycle status.
-- For excluded-company matches: the job matched but the user excluded that
-- company, so we inform them (Slack) and the application terminates here — it
-- never enters the apply lifecycle. This is a genuine terminal PHASE (on the
-- lifecycle axis), NOT the cut `notify_only` MODE. See DESIGN_NOTES.md.

BEGIN;

ALTER TABLE user_jobs DROP CONSTRAINT user_jobs_status_check;
ALTER TABLE user_jobs ADD CONSTRAINT user_jobs_status_check CHECK (status IN (
    'matched','preparing','ready','submitting','awaiting_review','submitted','abandoned','notified'
));

COMMIT;
