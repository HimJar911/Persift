-- migrations/007_user_jobs_additions.sql
-- Part 1: resume_snapshots table
-- Part 2: new columns on user_jobs (ML snapshots, app-time features, stage denorm)
-- Part 3: trigger function update_user_job_current_stage (not yet attached — see 008)
-- Part 4: indexes on user_jobs

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 1: resume_snapshots
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE resume_snapshots (
    id                SERIAL      PRIMARY KEY,
    user_id           UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    version_number    INT         NOT NULL,
    resume_text       TEXT        NOT NULL,
    resume_structured JSONB                DEFAULT '{}',
    is_active         BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, version_number)
);

CREATE INDEX idx_resume_snapshots_user_id
    ON resume_snapshots(user_id);

CREATE INDEX idx_resume_snapshots_active
    ON resume_snapshots(user_id, is_active)
    WHERE is_active = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 2: new columns on user_jobs
-- ─────────────────────────────────────────────────────────────────────────────

-- ML input snapshots (frozen at submission time)
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS resume_text_snapshot   TEXT;
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS tailored_resume_text   TEXT;
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS jd_text_snapshot       TEXT;
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS user_profile_snapshot  JSONB DEFAULT '{}';
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS resume_snapshot_id     INT
    REFERENCES resume_snapshots(id);

-- Application-time features for ML
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS days_since_posting     INT;
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS hour_submitted         SMALLINT
    CHECK (hour_submitted BETWEEN 0 AND 23);
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS day_of_week            SMALLINT
    CHECK (day_of_week BETWEEN 0 AND 6);
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS submission_mode        TEXT
    CHECK (submission_mode IN ('review_before_submit', 'autonomous'));
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS application_metadata   JSONB DEFAULT '{}';

-- Current stage denormalization (maintained by trigger attached in 008)
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS current_stage          TEXT;
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS current_stage_entered_at TIMESTAMPTZ;
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS latest_outcome_id      INT;

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 3: trigger function (attached in migration 008 once application_outcomes exists)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_user_job_current_stage()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE user_jobs
    SET
        current_stage            = NEW.outcome_type,
        current_stage_entered_at = NEW.outcome_date,
        latest_outcome_id        = NEW.id,
        updated_at               = NOW()
    WHERE id = NEW.user_job_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 4: indexes on user_jobs
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_user_jobs_user_current_stage
    ON user_jobs(user_id, current_stage);

CREATE INDEX IF NOT EXISTS idx_user_jobs_user_applied_at
    ON user_jobs(user_id, applied_at DESC);
