-- migrations/021_company_poll_log.sql
-- Append-only per-attempt poll history for companies, one row per (slug, ats)
-- poll attempt. Existing signal was too thin to diagnose why only 269/2,127
-- seeded Greenhouse companies ever contributed a job: `companies.
-- consecutive_failures` only tracks a bare counter (no reason), and
-- `companies.last_polled_at` has been dead schema since it was added --
-- nothing in the codebase writes it. This table replaces "infer from
-- job first_seen_at + a column nothing updates" with a real, queryable
-- record of every poll attempt's outcome.

CREATE TABLE IF NOT EXISTS company_poll_log (
    id             BIGSERIAL   PRIMARY KEY,
    slug           TEXT        NOT NULL,
    ats            TEXT        NOT NULL,
    polled_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    outcome        TEXT        NOT NULL CHECK (outcome IN (
                       'ok_with_jobs', 'ok_zero_jobs', 'http_404',
                       'http_429', 'http_4xx', 'http_5xx', 'timeout',
                       'connection_error', 'other_exception'
                   )),
    http_status    INTEGER,
    job_count      INTEGER     NOT NULL DEFAULT 0,
    matched_count  INTEGER     NOT NULL DEFAULT 0,  -- jobs after is_intern_role filter
    error_detail   TEXT
);

CREATE INDEX IF NOT EXISTS idx_company_poll_log_slug_ats ON company_poll_log (slug, ats, polled_at DESC);
CREATE INDEX IF NOT EXISTS idx_company_poll_log_outcome ON company_poll_log (outcome);
CREATE INDEX IF NOT EXISTS idx_company_poll_log_polled_at ON company_poll_log (polled_at DESC);
