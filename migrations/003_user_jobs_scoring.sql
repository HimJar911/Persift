-- migrations/003_user_jobs_scoring.sql

ALTER TABLE user_jobs ADD COLUMN relevance_score   SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE user_jobs ADD COLUMN keyword_match_data JSONB    NOT NULL DEFAULT '{}';
