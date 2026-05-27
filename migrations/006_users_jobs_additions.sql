-- migrations/006_users_jobs_additions.sql
-- Promote heavily-queried user profile fields to structured columns alongside
-- existing JSONB. Add JD capture and lifecycle columns to jobs.

-- ─────────────────────────────────────────────────────────────────────────────
-- users — structured profile columns
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE users ADD COLUMN IF NOT EXISTS requires_sponsorship  BOOLEAN;
ALTER TABLE users ADD COLUMN IF NOT EXISTS work_auth_type        TEXT
    CHECK (work_auth_type IN (
        'us_citizen', 'green_card', 'h1b', 'cpt', 'opt', 'other'
    ));
ALTER TABLE users ADD COLUMN IF NOT EXISTS available_start_date  DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS university            TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS graduation_date       DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS major                 TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS cohort_signup_week    DATE;

-- Backfill cohort_signup_week from existing created_at values
UPDATE users
SET cohort_signup_week = date_trunc('week', created_at)::DATE
WHERE cohort_signup_week IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- jobs — JD capture and lifecycle columns
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS jd_structured       JSONB;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS jd_captured_at      TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS last_seen_at        TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS estimated_fill_date TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS extractor_version   TEXT;
