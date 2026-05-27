-- migrations/009_indexes.sql
-- Deferred indexes across all tables, added once all tables exist.
-- No new tables or columns — indexes only.

-- ─────────────────────────────────────────────────────────────────────────────
-- user_jobs
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_user_jobs_status
    ON user_jobs(status);

CREATE INDEX IF NOT EXISTS idx_user_jobs_current_stage_active
    ON user_jobs(user_id, current_stage)
    WHERE current_stage IN (
        'callback', 'oa_invite', 'phone_screen',
        'interview_stage', 'final_round'
    );

-- ─────────────────────────────────────────────────────────────────────────────
-- jobs
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_jobs_company_slug
    ON jobs(company_slug);

CREATE INDEX IF NOT EXISTS idx_jobs_posted_at
    ON jobs(posted_at DESC);

CREATE INDEX IF NOT EXISTS idx_jobs_last_seen_at
    ON jobs(last_seen_at DESC)
    WHERE last_seen_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_jobs_categories_gin
    ON jobs USING GIN(categories);

-- ─────────────────────────────────────────────────────────────────────────────
-- companies
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_companies_canonical_domain
    ON companies(canonical_domain)
    WHERE canonical_domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_companies_is_active
    ON companies(is_active, ats)
    WHERE is_active = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- users
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_users_cohort_signup_week
    ON users(cohort_signup_week);

CREATE INDEX IF NOT EXISTS idx_users_university
    ON users(university)
    WHERE university IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_requires_sponsorship
    ON users(requires_sponsorship)
    WHERE requires_sponsorship IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- resume_snapshots
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_resume_snapshots_user_version
    ON resume_snapshots(user_id, version_number DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- aggregate_benchmarks
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_benchmarks_computed_at
    ON aggregate_benchmarks(computed_at DESC);
