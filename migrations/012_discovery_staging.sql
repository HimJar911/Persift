CREATE TABLE discovery_staging (
    id SERIAL PRIMARY KEY,
    job_id TEXT NOT NULL,
    job_ats TEXT NOT NULL,
    company_name TEXT,
    apply_url TEXT,
    raw_job JSONB,
    staged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed BOOLEAN NOT NULL DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    result TEXT CHECK (result IN ('added', 'already_known', 'queued_manual', 'failed')),
    result_canonical_company_id UUID,
    worker_version TEXT,
    UNIQUE (job_id, job_ats)
);

CREATE INDEX idx_discovery_staging_unprocessed ON discovery_staging (staged_at) WHERE processed = FALSE;
CREATE INDEX idx_discovery_staging_processed_at ON discovery_staging (processed_at);