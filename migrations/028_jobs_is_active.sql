-- migrations/028_jobs_is_active.sql
-- Job-listing freshness flag, added after the Aug 7 test-harness investigation
-- found that a real and significant fraction (~12-17%) of real Greenhouse
-- application attempts fail with not_a_standard_greenhouse_form for a mundane
-- reason: the job was live when harvested into `jobs`, but has since expired
-- or been pulled on Greenhouse's own servers (confirmed via curl: Greenhouse
-- 302-redirects a dead listing's apply_url to /<company>?error=true). Since
-- matcher.py only ever checks a given job once (matcher_checked_at IS NULL
-- watermark — see pipeline/matcher.py), a job that dies after being matched
-- would otherwise sit in user_jobs as 'ready' and eventually get queued for a
-- real user, who'd hit the exact same dead-listing failure the harness did.
--
-- Mirrors companies.is_active (migration 001) — same shape, one level down.
-- Written FALSE by api/server.py's /jobs/claim liveness check (Greenhouse
-- only, for now — see its code comment) when a claimed job turns out to be
-- dead; read by pipeline/matcher.py's _fetch_recent_jobs() so a dead job is
-- never matched to a new user again.

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_jobs_is_active ON jobs (is_active) WHERE is_active = FALSE;
