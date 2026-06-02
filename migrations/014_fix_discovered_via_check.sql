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

ALTER TABLE companies DROP CONSTRAINT IF EXISTS companies_match_method_check;

ALTER TABLE companies ADD CONSTRAINT companies_match_method_check
    CHECK (match_method = ANY (ARRAY[
        'seed_manual',
        'slug_matched',
        'name_matched',
        'domain_confirmed',
        'new',
        'career_page_fingerprint'
    ]));
