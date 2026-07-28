"""26 companies from the ORIGINAL 767-job/116-usable-company corpus
(oc_compact_full.json) confirmed, by direct read of their field lists, to be
job-board chrome (cookie-consent banners, search/filter widgets, newsletter
signups, marketing lead-gen forms) rather than real Greenhouse application
forms — the same "apply_url lands on a listing page, not the real form" bug
documented in corpus/README.md, just not caught during the original Jul 17
2026 open-coding pass because that pass optimized for individual-field
correctness (see manual_field_index_tags.json's single alixpartners
rejection, e.g.), not a page-level real/junk classification.

Found while building oc_compact_full_v2.json (Step 3 of the full-volume
corpus extension, see STATE.md/plan): auto_cluster_v2.py's clustering
picked up a 106,946-field 'select' cluster and a 13-field 'search' cluster
that turned out to be React-Select "Select..." placeholder chrome and
job-search-box labels respectively — traced back to these 26 contaminating
companies (their fields' generic labels false-merged across companies, the
exact department_interest/location_preference failure mode already
documented in corpus_analysis/README.md, just via new example strings).

Every company below was individually read (its full field list, id/label/
itype/section) before being listed here — matches the same evidence
discipline as manual_field_index_tags.json. See STATE.md's session log for
the full read-through.

These companies' ORIGINAL (ci, fi)-keyed decisions in cluster_decisions.json
/ manual_field_index_tags.json / etc. are NOT deleted or modified — this
file only controls which companies get INCLUDED when building
oc_compact_full_v2.json going forward. The original file/decisions stay as
historical record; this is a v2-corpus-construction-time filter.
"""

EXCLUDED_ORIGINAL_JOB_IDS = {
    "6254480003",  # alixpartners — cookie-consent banner chrome only
    "7490274",     # asana — cookie-consent banner chrome only
    "4693319101",  # asm — job-listing search/filter widget chrome only
    "8016582",     # bugcrowd — cookie-consent banner chrome only
    "7938474",     # coupang — job-listing "Filter jobs" widget chrome only (same pattern confirmed on a sibling posting in the second-run corpus)
    "7704587",     # careers (Hell Energy) — job-board search/chatbot/save-job chrome only
    "5807803004",  # cribl — cookie-consent banner chrome only
    "4677393005",  # ensono — search + newsletter-signup + cookie-consent chrome
    "4668066005",  # golden-careers — CMS block/page metadata (hidden fields), no real form content
    "4867475101",  # gostudent — Cybot Cookiebot consent-dialog chrome only
    "7871724",     # hioscar — cookie-consent banner chrome only
    "7593707003",  # intersystems — search overlay + cookie-consent chrome only
    "5843594004",  # intrinsicrobotics — newsletter-signup + cookie-consent chrome
    "6659639003",  # motional — cookie-consent banner chrome only
    "4542432008",  # omnicomhealth — job-board search/filter widget chrome only
    "4620837005",  # opswat — nav search + language switcher + cookie-consent chrome
    "7812132",     # pindrop — marketing "request a demo" lead-gen form, not a job application
    "7253017",     # pinterestcareers — job-listing keyword/location/team filter chrome only
    "5128789008",  # scopely — search/chatbot + cookie-consent + newsletter chrome
    "8276676002",  # sendbird — cookie-consent banner chrome only
    "7671593003",  # sentinelone — language-selector + cookie-consent chrome only
    "7819332",     # spire — search + cookie-consent banner chrome only
    "8551285002",  # sumup — cookie-consent banner chrome only
    "4671537006",  # vast — job-listing dept/office filter + newsletter + cookie-consent chrome
    "5983688004",  # veterinaryemergencygroupst — CMS filter widget + cookie-consent chrome
    "8499298002",  # workato — all hidden/unlabeled fields, no real content extracted
    "7733928003",  # cityoffortworth — ASP.NET __VIEWSTATE listing page, not Greenhouse-rendered

    # Found later, during Step 5 residue review (STATE.md): the original
    # "no resume field" check that produced the 26 exclusions above was
    # capped at <=15 fields, missing larger junk pages. Widened to
    # "no resume field, any field count" and re-checked against companies
    # not already excluded — these 5 are the SAME companies already
    # confirmed junk via their second-run sibling postings
    # (triage_real_vs_junk_resolved.json), just also present as a separate
    # job_id in the original 767-job corpus.
    "8244421002",  # cannondesign — job-listing search/filter/sort chrome (confirmed identical pattern on sibling posting)
    "7875384",     # d2l — job-listing search/filter/high-contrast-toggle chrome (confirmed identical pattern on sibling posting)
    "4672455005",  # ogilvy — Drupal "edit-field-*" CRM widget page (confirmed identical pattern on sibling posting)
    "7590656",     # oneacrefund — newsletter-signup + job-listing filter chrome (confirmed identical pattern on sibling posting)
    "7236933",     # stripe — department-filter checkbox_group listing page (confirmed identical pattern on sibling posting)
}
