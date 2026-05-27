-- migrations/008_core_new_tables.sql
-- Creates 8 new tables and attaches the trigger function from migration 007.
-- Run order matters: application_outcomes first (trigger target), then the rest.

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE 1: application_outcomes
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE application_outcomes (
    id                    SERIAL      PRIMARY KEY,
    user_job_id           INT         NOT NULL REFERENCES user_jobs(id)
                              ON DELETE CASCADE,
    outcome_type          TEXT        NOT NULL CHECK (outcome_type IN (
                              'applied_confirmed', 'viewed', 'callback',
                              'oa_invite', 'phone_screen', 'interview_stage',
                              'final_round', 'offer', 'accepted', 'rejected',
                              'ghosted', 'withdrawn',
                              'application_withdrawn_by_employer',
                              'offer_negotiation', 'offer_expired'
                          )),
    outcome_date          TIMESTAMPTZ NOT NULL,
    outcome_source        TEXT        NOT NULL CHECK (outcome_source IN (
                              'manual', 'gmail_auto', 'extension_detected'
                          )),
    outcome_metadata      JSONB                DEFAULT '{}',
    -- Offer compensation (structured, not buried in JSONB)
    base_salary_usd       NUMERIC,
    equity_value_usd      NUMERIC,
    signing_bonus_usd     NUMERIC,
    offer_accepted        BOOLEAN,
    offer_deadline        TIMESTAMPTZ,
    decline_reason        TEXT,
    -- Append-only correction chain
    corrects_outcome_id   INT         REFERENCES application_outcomes(id),
    -- Previous stage for transition modeling
    previous_outcome_type TEXT,
    -- Gmail signal that triggered this outcome (if any) — FK added in 008 after gmail_signals exists
    triggering_signal_id  INT,
    confidence            NUMERIC(3,2) CHECK (confidence BETWEEN 0.00 AND 1.00),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_outcomes_user_job_id
    ON application_outcomes(user_job_id);
CREATE INDEX idx_outcomes_type_date
    ON application_outcomes(outcome_type, outcome_date);
CREATE INDEX idx_outcomes_active_stages
    ON application_outcomes(user_job_id)
    WHERE outcome_type IN (
        'callback', 'oa_invite', 'phone_screen',
        'interview_stage', 'final_round'
    );
CREATE INDEX idx_outcomes_metadata
    ON application_outcomes USING GIN (outcome_metadata);

-- ─────────────────────────────────────────────────────────────────────────────
-- ATTACH TRIGGER FROM MIGRATION 007
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TRIGGER trg_update_current_stage
    AFTER INSERT ON application_outcomes
    FOR EACH ROW
    EXECUTE FUNCTION update_user_job_current_stage();

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE 2: application_attempts
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE application_attempts (
    id             SERIAL      PRIMARY KEY,
    user_job_id    INT         NOT NULL REFERENCES user_jobs(id)
                       ON DELETE CASCADE,
    attempt_number SMALLINT    NOT NULL,
    started_at     TIMESTAMPTZ NOT NULL,
    ended_at       TIMESTAMPTZ,
    success        BOOLEAN,
    failure_stage  TEXT        CHECK (failure_stage IN (
                       'form_detection', 'field_filling',
                       'resume_upload', 'submission',
                       'confirmation_detection', 'timeout'
                   )),
    error_details  JSONB                DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_attempts_user_job_id
    ON application_attempts(user_job_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE 3: application_events
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE application_events (
    id             SERIAL      PRIMARY KEY,
    user_job_id    INT         NOT NULL REFERENCES user_jobs(id)
                       ON DELETE CASCADE,
    user_id        UUID        NOT NULL REFERENCES users(id)
                       ON DELETE CASCADE,
    event_type     TEXT        NOT NULL CHECK (event_type IN (
                       'resume_reviewed', 'resume_edited_manually',
                       'match_dismissed', 'match_snoozed',
                       'application_paused', 'application_resumed',
                       'notes_added', 'company_blacklisted'
                   )),
    event_metadata JSONB                DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_app_events_user_job_id
    ON application_events(user_job_id);
CREATE INDEX idx_app_events_user_id
    ON application_events(user_id, created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE 4: model_predictions
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE model_predictions (
    id                   SERIAL      PRIMARY KEY,
    user_job_id          INT         NOT NULL REFERENCES user_jobs(id)
                             ON DELETE CASCADE,
    predicted_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model_version        TEXT        NOT NULL,
    callback_probability NUMERIC(5,4) CHECK (
                             callback_probability BETWEEN 0.0 AND 1.0
                         ),
    predicted_stage      TEXT,
    feature_snapshot     JSONB                DEFAULT '{}',
    -- Filled in later when outcome arrives
    actual_outcome_type  TEXT,
    actual_outcome_date  TIMESTAMPTZ,
    prediction_error     NUMERIC,
    evaluated_at         TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_predictions_user_job_id
    ON model_predictions(user_job_id);
CREATE INDEX idx_predictions_model_version
    ON model_predictions(model_version, predicted_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE 5: gmail_authorizations
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE gmail_authorizations (
    id                 SERIAL      PRIMARY KEY,
    user_id            UUID        NOT NULL REFERENCES users(id)
                           ON DELETE CASCADE,
    oauth_scopes       TEXT[]      NOT NULL,
    granted_at         TIMESTAMPTZ NOT NULL,
    revoked_at         TIMESTAMPTZ,
    is_active          BOOLEAN     NOT NULL DEFAULT TRUE,
    access_token_hash  TEXT,
    refresh_token_hash TEXT,
    token_expires_at   TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_gmail_auth_user_id
    ON gmail_authorizations(user_id)
    WHERE is_active = TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE 6: gmail_signals
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE gmail_signals (
    id                     SERIAL      PRIMARY KEY,
    user_id                UUID        NOT NULL REFERENCES users(id)
                               ON DELETE CASCADE,
    gmail_authorization_id INT         REFERENCES gmail_authorizations(id),
    detected_at            TIMESTAMPTZ NOT NULL,
    email_date             TIMESTAMPTZ NOT NULL,
    sender_domain          TEXT        NOT NULL,
    subject_line           TEXT,
    was_classified_as      TEXT        NOT NULL CHECK (was_classified_as IN (
                               'callback', 'rejection', 'oa_invite',
                               'offer', 'interview_schedule',
                               'not_relevant', 'uncertain'
                           )),
    confidence             NUMERIC(3,2) CHECK (confidence BETWEEN 0.00 AND 1.00),
    detector_version       TEXT        NOT NULL,
    linked_application_id  INT         REFERENCES user_jobs(id),
    user_confirmed         BOOLEAN              DEFAULT NULL,
    user_correction        TEXT,
    correction_category    TEXT        CHECK (correction_category IN (
                               'wrong_outcome_type',
                               'wrong_application_matched',
                               'not_job_related',
                               'duplicate_detection',
                               'other'
                           )),
    purge_after            TIMESTAMPTZ,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_gmail_signals_user_id
    ON gmail_signals(user_id, detected_at DESC);
CREATE INDEX idx_gmail_signals_application
    ON gmail_signals(linked_application_id)
    WHERE linked_application_id IS NOT NULL;

-- Back-fill the FK from application_outcomes.triggering_signal_id now that
-- gmail_signals exists.
ALTER TABLE application_outcomes
    ADD CONSTRAINT fk_outcomes_triggering_signal
    FOREIGN KEY (triggering_signal_id) REFERENCES gmail_signals(id);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE 7: user_job_interactions
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE user_job_interactions (
    id                 SERIAL      PRIMARY KEY,
    user_id            UUID        NOT NULL REFERENCES users(id)
                           ON DELETE CASCADE,
    job_id             TEXT,
    job_ats            TEXT,
    raw_url            TEXT,
    interaction_type   TEXT        NOT NULL CHECK (interaction_type IN (
                           'viewed', 'clicked', 'saved',
                           'pasted_in', 'dismissed', 'shared'
                       )),
    source             TEXT        NOT NULL CHECK (source IN (
                           'extension_browse', 'dashboard_browse',
                           'user_paste', 'email_forward'
                       )),
    time_spent_seconds INT,
    session_id         TEXT,
    did_apply          BOOLEAN              DEFAULT FALSE,
    linked_user_job_id INT         REFERENCES user_jobs(id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_interactions_user_id
    ON user_job_interactions(user_id, created_at DESC);
CREATE INDEX idx_interactions_job
    ON user_job_interactions(job_id, job_ats)
    WHERE job_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE 8: aggregate_benchmarks
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE aggregate_benchmarks (
    id              SERIAL      PRIMARY KEY,
    metric_name     TEXT        NOT NULL,
    dimension       TEXT        NOT NULL,
    dimension_value TEXT        NOT NULL,
    value           NUMERIC     NOT NULL,
    sample_size     INT         NOT NULL DEFAULT 0,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (metric_name, dimension, dimension_value)
);

CREATE INDEX idx_benchmarks_metric
    ON aggregate_benchmarks(metric_name, dimension);
