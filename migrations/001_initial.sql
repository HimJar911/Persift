-- migrations/001_initial.sql
-- Full initial schema for Persift on Postgres 16.
-- Run with: psql $DATABASE_URL -f migrations/001_initial.sql

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ─────────────────────────────────────────────────────────────────────────────
-- companies
-- Slug registry for all polled ATS companies.
-- consecutive_failures auto-deactivates a company at 5 failures.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE companies (
    id                   SERIAL      PRIMARY KEY,
    ats                  TEXT        NOT NULL,
    slug                 TEXT        NOT NULL,
    name                 TEXT        NOT NULL DEFAULT '',
    is_active            BOOLEAN     NOT NULL DEFAULT TRUE,
    consecutive_failures INT         NOT NULL DEFAULT 0,
    last_polled_at       TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ats, slug)
);

CREATE INDEX idx_companies_ats_active ON companies (ats, is_active);


-- ─────────────────────────────────────────────────────────────────────────────
-- jobs
-- Canonical job record. sources[] handles cross-source dedup:
-- first hit wins for all scalar fields; subsequent ATS sources are appended.
-- posted_at is a millisecond epoch (Jobright); 0 means unknown.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE jobs (
    job_id           TEXT        NOT NULL,
    ats              TEXT        NOT NULL,
    company_slug     TEXT        NOT NULL,
    company_name     TEXT        NOT NULL DEFAULT '',
    title            TEXT        NOT NULL,
    location         TEXT        NOT NULL DEFAULT 'Unknown',
    apply_url        TEXT        NOT NULL DEFAULT '',
    description      TEXT        NOT NULL DEFAULT '',
    categories       TEXT[]      NOT NULL DEFAULT '{}',
    experience_level TEXT        NOT NULL DEFAULT '',
    work_model       TEXT        NOT NULL DEFAULT 'Unknown',
    h1b_sponsored    TEXT        NOT NULL DEFAULT 'Not Sure',
    posted_at        BIGINT      NOT NULL DEFAULT 0,
    sources          TEXT[]      NOT NULL DEFAULT '{}',
    first_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (job_id, ats)
);

CREATE INDEX idx_jobs_company_slug  ON jobs (company_slug);
CREATE INDEX idx_jobs_first_seen_at ON jobs (first_seen_at DESC);
CREATE INDEX idx_jobs_categories    ON jobs USING GIN (categories);
CREATE INDEX idx_jobs_experience    ON jobs (experience_level);


-- ─────────────────────────────────────────────────────────────────────────────
-- users
-- Full user profile. Multi-user architecture — not yet active in prod.
-- preferences / work_auth / application_settings stored as JSONB for flexibility.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE users (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email                TEXT        NOT NULL UNIQUE,
    tier                 TEXT        NOT NULL DEFAULT 'free'
                             CONSTRAINT users_tier_check CHECK (tier IN ('free', 'pro')),
    preferences          JSONB       NOT NULL DEFAULT '{}',
    resume_text          TEXT        NOT NULL DEFAULT '',
    work_auth            JSONB       NOT NULL DEFAULT '{}',
    application_settings JSONB       NOT NULL DEFAULT '{}',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ─────────────────────────────────────────────────────────────────────────────
-- user_jobs
-- Per-user application state machine.
-- Status flow: queued → applying → applied | failed | needs_review | dismissed
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE user_jobs (
    id                   SERIAL      PRIMARY KEY,
    user_id              UUID        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    job_id               TEXT        NOT NULL,
    job_ats              TEXT        NOT NULL,
    status               TEXT        NOT NULL DEFAULT 'queued'
                             CONSTRAINT user_jobs_status_check
                             CHECK (status IN ('queued', 'applying', 'applied', 'failed', 'needs_review', 'dismissed')),
    tailored_resume_path TEXT,
    notes                TEXT,
    applied_at           TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (job_id, job_ats) REFERENCES jobs (job_id, ats) ON DELETE CASCADE,
    UNIQUE (user_id, job_id, job_ats)
);

CREATE INDEX idx_user_jobs_user_status ON user_jobs (user_id, status);


-- ─────────────────────────────────────────────────────────────────────────────
-- poller_state
-- Replaces persift_jobright_state.json (and any future on-disk cursor files).
-- cursor stores poller-specific checkpoint data, e.g. {"since_ms": 1716000000000}
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE poller_state (
    poller      TEXT        PRIMARY KEY,
    last_run_at TIMESTAMPTZ,
    cursor      JSONB       NOT NULL DEFAULT '{}'
);
