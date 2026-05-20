-- migrations/002_indexes.sql

-- Partial index for the tailor worker hot path — only indexes queued rows,
-- so the scan stays tiny as rows transition out of queued status.
CREATE INDEX idx_user_jobs_queued ON user_jobs (created_at)
WHERE status = 'queued';

-- Retry counter for failed tailor calls — enables backoff and distinguishes
-- transient API errors from permanently bad job descriptions.
ALTER TABLE user_jobs ADD COLUMN retry_count SMALLINT NOT NULL DEFAULT 0;

-- GIN indexes on preferences JSONB for future push-filter-to-SQL work.
CREATE INDEX idx_users_pref_categories  ON users USING GIN ((preferences->'categories'));
CREATE INDEX idx_users_pref_work_models ON users USING GIN ((preferences->'work_models'));
