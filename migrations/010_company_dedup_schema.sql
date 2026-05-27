-- migrations/010_company_dedup_schema.sql
-- Part 1: match_method and match_confidence columns on companies.
-- Part 2: company_merge_candidates table for cross-ATS dedup review queue.

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 1: new columns on companies
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE companies ADD COLUMN IF NOT EXISTS match_method TEXT
    CHECK (match_method IN (
        'seed_manual', 'slug_matched', 'name_matched',
        'domain_confirmed', 'new'
    ));

ALTER TABLE companies ADD COLUMN IF NOT EXISTS match_confidence TEXT
    CHECK (match_confidence IN ('high', 'medium', 'unverified'));

-- ─────────────────────────────────────────────────────────────────────────────
-- PART 2: company_merge_candidates
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE company_merge_candidates (
    id                    SERIAL      PRIMARY KEY,
    canonical_id_a        UUID        NOT NULL
                              REFERENCES companies(canonical_company_id),
    canonical_id_b        UUID        NOT NULL
                              REFERENCES companies(canonical_company_id),
    company_name_a        TEXT        NOT NULL,
    company_name_b        TEXT        NOT NULL,
    name_similarity_score NUMERIC(4,3) CHECK (
                              name_similarity_score BETWEEN 0 AND 1
                          ),
    apply_url_a           TEXT,
    apply_url_b           TEXT,
    triggered_by          TEXT        NOT NULL CHECK (triggered_by IN (
                              'name_fuzzy_match',
                              'slug_match_cross_ats',
                              'manual_flag'
                          )),
    verified              BOOLEAN              DEFAULT NULL,
    verified_at           TIMESTAMPTZ,
    verified_by           TEXT        CHECK (verified_by IN (
                              'builtwith', 'manual', 'domain_match'
                          )),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (canonical_id_a, canonical_id_b)
);

CREATE INDEX idx_merge_candidates_unverified
    ON company_merge_candidates(created_at)
    WHERE verified IS NULL;

CREATE INDEX idx_merge_candidates_id_a
    ON company_merge_candidates(canonical_id_a);

CREATE INDEX idx_merge_candidates_id_b
    ON company_merge_candidates(canonical_id_b);
