-- migrations/005_companies_redesign.sql
-- Redesign companies table: introduce canonical_company_id UUID as the real PK.
-- The old SERIAL id + slug-only uniqueness could not represent the same company
-- slug existing on multiple ATS platforms (e.g. "stripe" on Greenhouse and Lever).
-- The new PK is a UUID; business uniqueness is enforced by UNIQUE (slug, ats).

-- 1. Add UUID column (nullable first so backfill can run)
ALTER TABLE companies ADD COLUMN canonical_company_id UUID;

-- 2. Backfill — every existing row gets its own UUID
UPDATE companies SET canonical_company_id = gen_random_uuid()
WHERE canonical_company_id IS NULL;

-- 3. Lock it down
ALTER TABLE companies ALTER COLUMN canonical_company_id SET NOT NULL;

-- 4. Drop old primary key (SERIAL id)
ALTER TABLE companies DROP CONSTRAINT companies_pkey;

-- 5. Promote canonical_company_id to primary key
ALTER TABLE companies ADD PRIMARY KEY (canonical_company_id);

-- 6. Replace slug-only uniqueness with (slug, ats) composite unique constraint.
-- Drop the old UNIQUE (ats, slug) from migration 001 first to avoid a duplicate.
ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_ats_slug_key;
ALTER TABLE companies ADD CONSTRAINT companies_slug_ats_unique UNIQUE (slug, ats);

-- 7. New enrichment columns
ALTER TABLE companies ADD COLUMN IF NOT EXISTS canonical_domain  TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS industry          TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS headcount_range   TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS discovered_via    TEXT
    CHECK (discovered_via IN (
        'direct_seed', 'jobright_seeded', 'user_browsing',
        'manual', 'builtwith_lookup'
    ));
ALTER TABLE companies ADD COLUMN IF NOT EXISTS discovered_at     TIMESTAMPTZ;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS posting_velocity  NUMERIC;

-- 8. Index for canonical_domain dedup lookups
CREATE INDEX IF NOT EXISTS idx_companies_canonical_domain ON companies (canonical_domain);
