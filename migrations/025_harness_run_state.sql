-- migrations/025_harness_run_state.sql
-- Self-healing test pipeline (test_pipeline/): tracks per-run and per-job
-- state for the Playwright harness that drives the real Chrome extension
-- against real, previously-untested job postings (fill+verify only, never
-- submit). Deliberately NOT layered onto user_jobs.status — that table's
-- CHECK constraint and _RETRY_CAP (api/server.py) encode real product
-- lifecycle semantics tied to /jobs/claim's FIFO logic, and conflating
-- harness test runs with genuine application data risks corrupting both.
-- Same precedent as corpus_crawl_state (migration 020): a clean new table,
-- absence of a row means "never attempted," resumable via a status filter.
--
-- outcome is deliberately named with 'mechanically_verified', not
-- 'clean'/'success' — the harness's own verification is mechanical only
-- (did a value land in the field), never semantic (is it the RIGHT value).
-- See decisions/0010-verification-is-mechanical-not-semantic.md. Naming it
-- honestly at the schema level means no downstream report/dashboard can
-- accidentally treat "verified" as "correct".

CREATE TABLE IF NOT EXISTS harness_runs (
    id                     SERIAL      PRIMARY KEY,
    started_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ats                    TEXT        NOT NULL,
    target_count           INTEGER     NOT NULL,
    harness_version        TEXT        NOT NULL,
    -- Version-stamping beyond harness_version so two checkpoints from
    -- different points in time (e.g. an August run vs. an October run)
    -- are directly comparable, not just "the harness ran twice."
    interpreter_version    TEXT,       -- hash of corpus_analysis/interpreter_p14.py at run start
    extension_commit_sha   TEXT,       -- git commit of extension/ loaded into the workers
    regression_corpus_size INTEGER,    -- interpreter_regressions.json entry count at run start
    notes                  TEXT
);

CREATE TABLE IF NOT EXISTS harness_job_state (
    run_id           INTEGER     NOT NULL REFERENCES harness_runs (id) ON DELETE CASCADE,
    job_id           TEXT        NOT NULL,
    ats              TEXT        NOT NULL,
    sample_phase     TEXT        NOT NULL CHECK (sample_phase IN ('A', 'B')),
    -- Phase A = random sample (baseline robustness).
    -- Phase B = targeted long-tail sample built from corpus_analysis/
    -- clusters_v2.json's per-category rarity data (rare-structure bug
    -- discovery). Kept as separate, comparable populations, not blended.
    worker_id        INTEGER,
    outcome          TEXT        NOT NULL DEFAULT 'pending' CHECK (outcome IN (
                          'pending', 'mechanically_verified', 'needs_review_non_submit',
                          'failed', 'timeout', 'harness_error', 'skipped_blocked'
                      )),
    -- mechanically_verified = extension reached awaiting_review/
    --   awaiting_user_submit AND the harness's independent verification
    --   script confirmed every attempted field has a non-empty landed
    --   value. Does NOT mean the value is semantically correct.
    -- needs_review_non_submit = awaiting_review reached for a reason
    --   other than awaiting_user_submit (e.g. no form found) — a
    --   graceful bail, not a crash.
    -- failed = background.js's case 'failed' ran.
    -- timeout = the harness's own ~90s ceiling was hit; job was
    --   force-released via POST /jobs/{id}/released.
    -- harness_error = a Playwright/infra exception, not a real signal
    --   from the extension itself.
    -- skipped_blocked = never attempted because the circuit breaker
    --   tripped on a page-level block signature first.
    phase_reached    TEXT,        -- last observed chrome.storage.local phase
    failure_reason   TEXT,        -- reason string from the 'failed'/'needs_review' message
    fields_filled    INTEGER,
    fields_total     INTEGER,
    page_fingerprint TEXT,        -- coarse structural page-layout fingerprint (see harness_runner.py)
    started_at       TIMESTAMPTZ,
    ended_at         TIMESTAMPTZ,
    debug_log_ref    TEXT,        -- path to the saved debug_log JSON dump for this job, if any
    harness_version  TEXT        NOT NULL,
    PRIMARY KEY (run_id, job_id, ats),
    FOREIGN KEY (job_id, ats) REFERENCES jobs (job_id, ats) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_harness_job_state_pending
    ON harness_job_state (run_id) WHERE outcome = 'pending';
CREATE INDEX IF NOT EXISTS idx_harness_job_state_outcome
    ON harness_job_state (run_id, outcome);
CREATE INDEX IF NOT EXISTS idx_harness_job_state_phase
    ON harness_job_state (run_id, sample_phase, outcome);
