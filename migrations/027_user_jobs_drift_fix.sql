-- migrations/027_user_jobs_drift_fix.sql
-- Real schema drift found while live-testing test_pipeline/job_driver.py
-- against a fresh VM built purely by replaying migrations/*.sql in order:
-- the VM's user_jobs table was missing failure_reason and ats_format_issues
-- entirely, even though api/server.py (e.g. /jobs/{id}/released writes
-- failure_reason) and pipeline/formatter.py (ats_format_issues) both depend
-- on them existing. Neither column was ever added via a tracked migration —
-- grep of migrations/*.sql confirms no ALTER TABLE ADD COLUMN for either
-- name; they exist on the long-running local dev DB only because they were
-- added by hand at some point before migrations were the source of truth.
-- A full column diff (local vs. VM) confirmed users/jobs/companies match;
-- user_jobs was the only table affected.

ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS failure_reason TEXT;
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS ats_format_issues JSONB DEFAULT '[]'::jsonb;
