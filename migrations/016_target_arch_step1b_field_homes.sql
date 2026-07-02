-- Migration 016 — Target Architecture, Step 1b: field homes (JSONB -> columns).
-- The founding-bug fix: collapse each profile fact to ONE home per the
-- Column-vs-JSONB rule. Conflict-free — the migration-006 columns are all EMPTY;
-- all real data is in application_settings JSONB (verified July 1, 2026).
-- Atomic: all-or-nothing. See DESIGN_NOTES.md Migration path step 1b.

BEGIN;

-- --- Schema: add the columns the design wants as first-class facts ---
ALTER TABLE users ADD COLUMN IF NOT EXISTS gpa                 NUMERIC(3,2);
ALTER TABLE users ADD COLUMN IF NOT EXISTS visa_type           TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS location_city       TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS location_state      TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS location_preference TEXT;  -- local|remote|anywhere (NEW; no data yet)

ALTER TABLE users ADD CONSTRAINT users_location_preference_check
    CHECK (location_preference IS NULL
           OR location_preference IN ('local', 'remote', 'anywhere'));

-- --- Rename requires_sponsorship -> needs_sponsorship (empty col; match JSONB + design) ---
ALTER TABLE users RENAME COLUMN requires_sponsorship TO needs_sponsorship;
ALTER INDEX idx_users_requires_sponsorship RENAME TO idx_users_needs_sponsorship;

-- --- Drop the dead, never-populated work_auth_type enum (third vocabulary; unused) ---
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_work_auth_type_check;
ALTER TABLE users DROP COLUMN work_auth_type;

-- --- Data move: JSONB -> columns (the single populated home wins) ---
UPDATE users SET
    university        = application_settings->>'school',
    major             = application_settings->>'major',
    gpa               = (application_settings->>'gpa')::numeric,
    -- canonical date: "May 2027" -> 2027-05-01 (day is a harmless anchor; see DESIGN_NOTES)
    graduation_date   = to_date(application_settings->>'graduation_date', 'Mon YYYY'),
    needs_sponsorship = (application_settings->>'needs_sponsorship')::boolean,
    visa_type         = application_settings->>'visa_type',
    location_city     = application_settings->>'location_city',
    location_state    = application_settings->>'location_state';

-- --- Strip the moved keys from JSONB so each fact has exactly ONE home ---
UPDATE users SET application_settings = application_settings
    - 'school'
    - 'major'
    - 'gpa'
    - 'graduation_date'
    - 'needs_sponsorship'
    - 'visa_type'
    - 'location_city'
    - 'location_state';

COMMIT;
