"""Provisional canonical category enum — taxonomy_v1.

Formalizes the ~110+ categories that previously only existed scattered
across corpus_analysis/'s decision JSON files (cluster_decisions.json's
"confirm" bucket, manual_field_index_tags.json, manual_singleton_tags.json,
correction_department_location.json) into one real, versioned list.

Built BEFORE any LLM-assisted residue classification runs (Step 5 of the
full-volume corpus-extension plan, see STATE.md) — deliberately, so the LLM
classifies against a fixed vocabulary instead of inventing synonyms/
near-duplicate categories for genuinely-new field types. Marked
"provisional" because Step 5's residue pass is expected to surface real
categories the original 767-job sample never saw; those get reviewed and
added as taxonomy_v2 (see TAXONOMY_VERSION below and
corpus_analysis/README.md for the version-bump process), not silently
appended mid-classification.

Every field decision from Step 5 onward should record which
TAXONOMY_VERSION it was classified against (see backfill_stable_keys.py's
decision_source field for the parallel provenance-tracking pattern).

Two kinds of entries, per FORM_ENGINE_DESIGN.md §7's standing distinction:

1. TOPIC_CATEGORIES — "ask the user this fact" categories. A category here
   means: given a resolved field of this category, resolveValue() looks up
   one fact in the user's profile and fills it.
2. STRUCTURAL_PATTERNS — NOT topics. These describe a structural
   relationship or a non-interactive pattern that needs its own
   resolution-layer handling, not a profile lookup. Building these as if
   they were ordinary categories was explicitly flagged as the wrong shape
   in FORM_ENGINE_DESIGN.md §7 (e.g. other_followup) — kept separate here
   so that mistake isn't repeated when this enum feeds P1.4.
"""

TAXONOMY_VERSION = "v1"

# --- Categories proposed during Step 5's residue review, pending a version
# bump to v2 once Step 5 fully concludes (see plan: new categories get
# reviewed and added deliberately, not silently appended mid-classification).
# Kept in a separate set so it's clear which categories were in the
# original 767-job-derived v1 vs. newly proposed from the full-volume
# residue pass.
PROPOSED_V2_ADDITIONS = {
    "consent_privacy_policy": (
        "Checkbox consent to a company's privacy policy — distinct from "
        "consent_background_check (background check specifically) and "
        "consent_ccpa_share_sale (CCPA data-sale opt-out specifically). "
        "Found during Step 5 residue review: 230 instances across 2 "
        "companies (Qube Research and Technologies, Axon), always a "
        "checkbox_group whose only content is a section header literally "
        "reading 'Privacy Policy *' — no label/options/nearby text, the "
        "section header IS the question."
    ),
    "consent_gdpr_notice": (
        "Checkbox/combobox acknowledgment of a GDPR data-processing "
        "notice — distinct from consent_ccpa_share_sale (US CCPA-specific) "
        "since GDPR is the EU regime with different disclosure text/scope. "
        "Found during Step 5 residue review (globalrelay: 'GDPR Notice*')."
    ),
    "visa_type": (
        "What type/category of visa the applicant currently holds (e.g. "
        "H-1B, F-1, OPT, TN) — distinct from needs_sponsorship (yes/no "
        "future sponsorship need) and citizenship_status (nationality/"
        "citizenship). Found during Step 6 held-out validation gap "
        "resolution: 'If yes, please note your current visa status' / "
        "'If yes, please enter visa type' follow-up fields."
    ),
}

# --- Topic categories: 118 confirmed via the original 767-job open-coding
# pass (cluster_decisions.json's "confirm" bucket + manual_field_index_tags/
# manual_singleton_tags/correction_department_location's confirmed
# entries). Counts are original-corpus field counts, NOT full-volume counts
# — informational only (which categories were common vs. rare in the seed
# sample), not a claim about their frequency in the full 633K-field corpus.
TOPIC_CATEGORIES = {
    "academic_grade", "age_18_or_older", "agency_preference",
    "ai_tool_usage_disclosure", "attention_check",
    "availability_commitment_confirmation", "availability_days",
    "availability_end_date", "availability_hours_per_week",
    "availability_start_date", "ccpa_california_disclosure",
    "certifications", "citizenship_status",
    "compensation_range_acknowledgment", "competing_offers_disclosure",
    "competition_participation", "consent_attestation_general",
    "consent_background_check", "consent_ccpa_share_sale",
    "consent_sms_communication", "contract_length", "country_of_origin",
    "country_of_residence", "courses_remaining", "cover_letter_upload",
    "criminal_background_disclosure", "current_benefits", "current_company",
    "current_country_id_number", "current_employee_of_company",
    "current_job_title", "current_salary", "current_school_year",
    "currently_based_in_country", "currently_employed_elsewhere",
    "currently_enrolled_status", "department_interest", "education_degree",
    "education_discipline", "education_end_date", "education_school",
    "education_start_date", "eeo_disability_status", "eeo_gender_identity",
    "eeo_generic_decline_option", "eeo_hispanic_latino",
    "eeo_race_ethnicity", "eeo_sexual_orientation", "eeo_transgender",
    "eeo_veteran_status", "email", "employee_referral", "employment_type",
    "essay", "event_attendance", "export_control",
    "field_of_study_relevance", "first_name", "github_url",
    "graduation_date", "how_heard_about_role", "intended_work_country",
    "internship_agreement_confirmation", "interview_availability",
    "language_proficiency", "last_name", "linkedin_url", "location_city",
    "location_preference", "mailing_address",
    "marketing_communications_optin", "military_branch", "military_rank",
    "military_separation_date", "military_specialty_code",
    "military_time_in_service", "name_pronunciation", "national_id_number",
    "nationality", "nationality_check", "needs_sponsorship",
    "nepotism_disclosure", "notice_period", "pep_disclosure",
    "personal_website", "phone", "phone_country_code",
    "preferred_contact_method", "preferred_first_name",
    "preferred_pronouns", "previously_applied_here",
    "previously_employed_here", "program_affiliation", "publication_list",
    "qualifications_confirmation", "relevant_industry_experience",
    "resume_upload", "salary_expectation", "scholarship_program_affiliation",
    "security_clearance", "skill_experience_years",
    "skillbridge_eligibility_date", "standardized_test_score", "state",
    "street_address", "student_org_involvement", "technical_skills",
    "travel_willingness", "willing_to_relocate", "work_authorized",
    "work_history_employer", "work_history_end_date",
    "work_history_start_date", "work_history_title", "workplace_type",
    "writing_sample_request", "zip_code",
}

# --- Structural (non-topic) patterns — need resolution-layer handling, not
# a profile-fact lookup. See FORM_ENGINE_DESIGN.md §7 for the full
# rationale on each.
STRUCTURAL_PATTERNS = {
    "other_followup": (
        "Free-text follow-up to a preceding 'Other' choice. The field's own "
        "label carries no information — resolve by finding the nearest "
        "preceding field's selected value, not by classifying this field's "
        "label text."
    ),
    "honeypot": (
        "Anti-bot trap field (e.g. id=edit-url, label literally instructs "
        "'leave this field blank'). Must be actively skipped, never filled."
    ),
    "react_select_required_shim": (
        "Library-injected hidden required-input trailing a custom "
        "combobox, used only to let native HTML5 required-validation fire. "
        "Not askable — resolves itself once the combobox it shims is "
        "filled. Confirmed (FORM_ENGINE_DESIGN.md §7) to also appear with "
        "label populated by a buggy 'preceding-text' label-strategy match "
        "on the widget's own 'Select...' placeholder text, not just "
        "label=='' — both are the same pattern (see corpus_analysis/"
        "auto_cluster_v2.py's normalize handling, found during the "
        "full-volume re-run)."
    ),
    "hidden_tracking_field": (
        "Hidden marketing/analytics fields (gclid, ft_source, ft_campaign, "
        "lt_source, lead_source, gaclientid, etc.) — always itype=hidden, "
        "never user-facing, never askable. Found at full-volume re-run "
        "clustering (Step 3): consistently hidden across ~4,665-field "
        "clusters each, one distinct field per tracking-parameter name, "
        "not previously seen as a class in the 767-job seed sample. "
        "Provisional — not yet split into fully enumerated named fields, "
        "just flagged as a class needing a blanket "
        "skip-don't-classify-as-a-question rule."
    ),
}
