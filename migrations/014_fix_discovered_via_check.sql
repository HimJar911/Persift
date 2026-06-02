ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_discovered_via_check;

ALTER TABLE companies ADD CONSTRAINT companies_discovered_via_check
    CHECK (discovered_via = ANY (ARRAY[
        'direct_seed',
        'jobright_seeded',
        'user_browsing',
        'manual',
        'builtwith_lookup',
        'fingerprint'
    ]));
