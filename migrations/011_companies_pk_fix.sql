-- migrations/011_companies_pk_fix.sql
-- canonical_company_id is not a true PK because multiple companies rows can
-- share the same UUID (one per real-world company × ATS platform).
-- Fix: drop FKs that reference it, demote it to a regular indexed column,
-- and restore the original SERIAL id as the surrogate PK.
--
-- company_merge_candidates.canonical_id_a/b become plain UUID columns — they
-- still store the logical company UUID, just without FK enforcement (since the
-- referenced column is no longer unique).

-- 1. Drop FK constraints on company_merge_candidates that block the PK change
ALTER TABLE company_merge_candidates
    DROP CONSTRAINT company_merge_candidates_canonical_id_a_fkey;

ALTER TABLE company_merge_candidates
    DROP CONSTRAINT company_merge_candidates_canonical_id_b_fkey;

-- 2. Drop the PK on canonical_company_id
ALTER TABLE companies DROP CONSTRAINT companies_pkey;

-- 3. Promote the existing SERIAL id column back to primary key
--    (id was created in migration 001, demoted in 005 — it still exists)
ALTER TABLE companies ADD COLUMN IF NOT EXISTS id SERIAL;
ALTER TABLE companies ADD PRIMARY KEY (id);

-- 4. Index canonical_company_id for group-by / lookup queries
CREATE INDEX IF NOT EXISTS idx_companies_canonical_id
    ON companies(canonical_company_id);
