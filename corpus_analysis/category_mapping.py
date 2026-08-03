"""P1.4 — ontology-to-capability mapping.

taxonomy_v1.py's 118 TOPIC_CATEGORIES are an ONTOLOGY: they answer "what is
this field actually asking, semantically, in the real world?" — built
bottom-up from reading real corpus fields, with no reference to what the
product can currently do with the answer.

extension/filler_utils.js's resolveValue() switch statement is a PRODUCT
CAPABILITY INTERFACE: it answers "what can the product currently look up
in a user's profile and fill in?" Its category names are load-bearing
across a 3-way naming contract (ARCHITECTURE.md "Invariants": resolveValue()
category keys <-> getProfile() JSON keys <-> application_settings JSONB
keys) — renaming one requires renaming all three.

These are not the same list and were never meant to be. A capability can
correspond to one ontology category; an ontology category can legitimately
have no capability behind it yet (marked UNSUPPORTED below). Reconciling
them into one unified vocabulary is explicitly OUT OF SCOPE for P1.4 (see
the P1.4 plan's "Explicit non-goals") — that would make this task
simultaneously an interpreter-design task AND an API/database/extension
migration, two different projects.

This file is the one place the two vocabularies actually meet, so each
entry carries a `rationale` and a `reviewed` flag, not just a bare target
name — a future reader needs to be able to tell "carefully reconciled,
confirmed same underlying fact" from "best guess, never verified." Checked
directly against resolveValue()'s ~30 real case statements
(extension/filler_utils.js lines 973-1191) while building this file: the
overlap is NOT mostly 1:1 pass-through — nearly every category that exists
in both places uses a different name.

interpreter_p14.py imports MAPPING to translate whatever ontology-shaped
signal it derives (label text, autocomplete tokens, etc.) into the
resolveValue-vocabulary category interpret() actually returns. An
UNSUPPORTED mapping must never leak into interpret()'s return value —
verified in replay's own checks, see P1.4 plan Verification step 5.
"""

from dataclasses import dataclass
from typing import Optional

TAXONOMY_VERSION_MAPPED_AGAINST = "v1"

UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class Mapping:
    ontology: str
    capability: str  # a real resolveValue() category name, or UNSUPPORTED
    rationale: str
    reviewed: bool  # True = read both sides and confirmed same underlying fact;
                     # False = plausible best-guess, not independently verified


# --- Structural patterns (taxonomy_v1.STRUCTURAL_PATTERNS) are NOT mapped
# here — they don't resolve to a profile fact at all, they resolve to an
# ACTION (skip / resolve-from-preceding-field / self-resolves). See
# interpreter_p14.py's detect_structural_pattern(). Mapping them into a
# fake "capability" would repeat the exact mistake FORM_ENGINE_DESIGN.md
# §7 already flagged for other_followup.

_MAPPINGS = [
    # --- Basic identity/contact — clean 1:1s, straightforward to verify.
    Mapping("first_name", "first_name", "Same fact, same name.", True),
    Mapping("last_name", "last_name", "Same fact, same name.", True),
    Mapping("preferred_first_name", "preferred_name", "resolveValue's 'preferred_name' falls back to first_name if unset — same concept as the ontology's preferred_first_name.", True),
    Mapping("email", "email", "Same fact, same name.", True),
    Mapping("phone", "phone", "Same fact, same name.", True),
    Mapping("phone_country_code", UNSUPPORTED, "resolveValue's 'phone' case delegates to fillIntlPhone() which resolves country code internally from profile.location_country; there is no standalone phone_country_code capability/case.", True),
    Mapping("linkedin_url", "linkedin", "Same fact; resolveValue's case is named 'linkedin' not 'linkedin_url'.", True),
    Mapping("github_url", "github", "Same fact; resolveValue's case is named 'github' not 'github_url'.", True),
    Mapping("personal_website", "portfolio", "resolveValue's 'portfolio' case reads profile.portfolio_url — same underlying fact as the ontology's personal_website.", True),
    Mapping("location_city", "location_city", "Same fact, same name.", True),
    Mapping("state", "location_state", "Ontology's bare 'state' and resolveValue's 'location_state' both resolve profile.location_state (abbr -> full name via US_STATES).", True),
    Mapping("street_address", "location_address", "Same fact; resolveValue's case is named 'location_address'.", True),
    Mapping("zip_code", "location_zip", "Same fact; resolveValue's case is named 'location_zip'.", True),
    Mapping("country_of_residence", "location_country", "resolveValue's 'location_country' resolves profile.location_country — matches 'what country do you currently reside in', which is what country_of_residence asks.", True),
    Mapping("mailing_address", "location_address", "No separate 'mailing vs. current' distinction exists in the live profile schema — both resolve to the single location_address capability.", False),
    Mapping("preferred_pronouns", "pronouns", "Same fact; resolveValue's case is named 'pronouns' not 'preferred_pronouns'.", True),
    Mapping("name_pronunciation", UNSUPPORTED, "No capability/profile field for phonetic name pronunciation exists.", True),

    # --- Work authorization / immigration.
    Mapping("work_authorized", "work_authorized", "Same fact, same name — 'are you authorized to work' (short-term/current).", True),
    Mapping("needs_sponsorship", "needs_sponsorship", "Same fact, same name.", True),
    Mapping("citizenship_status", "work_authorized_longterm", "Ontology's citizenship_status (nationality/citizenship fact) is not the same fact as resolveValue's work_authorized_longterm (long-term/permanent work-authorization YES/NO derived from visa type) — mapped provisionally since it's the closest existing capability, but this is a real semantic gap, not a confirmed match. Flagging for review rather than treating as settled.", False),
    Mapping("intended_work_country", UNSUPPORTED, "No capability resolves 'which country do you intend to work in' as distinct from current location_country.", True),
    Mapping("currently_based_in_country", "location_country", "Same underlying fact as country_of_residence/location_country.", False),
    Mapping("country_of_origin", UNSUPPORTED, "Distinct fact from country_of_residence (birth/origin country vs. current residence) with no separate profile field.", True),
    Mapping("nationality", UNSUPPORTED, "No nationality capability exists separately from visa_status/work_authorized.", True),
    Mapping("nationality_check", UNSUPPORTED, "Same gap as nationality.", True),
    Mapping("national_id_number", UNSUPPORTED, "No PII field of this kind exists in the profile schema (and likely shouldn't be auto-filled without explicit product review, given the sensitivity).", True),
    Mapping("current_country_id_number", UNSUPPORTED, "Same gap as national_id_number.", True),
    Mapping("export_control", UNSUPPORTED, "ITAR/export-control citizenship questions have no dedicated capability — flagged separately in STATE.md's known issues ('ITAR filter missing in matcher') as a distinct, larger gap, not just a resolveValue case.", True),
    Mapping("security_clearance", UNSUPPORTED, "No security-clearance profile field exists.", True),
    Mapping("visa_type", "visa_status", "PROVISIONAL, NOT CONFIRMED SAME FACT — this is exactly the case flagged in the P1.4 plan as needing real reconciliation. taxonomy_v1's own docstring describes visa_type as 'what type/category of visa' (H-1B/F-1/OPT/TN), which sounds like the same underlying fact resolveValue's visa_status resolves (via VISA_ALIASES[profile.visa_type]) — but this has not been independently verified field-by-field, only inferred from both names/docstrings referencing 'visa'. Needs a real side-by-side check against corpus examples before trusting.", False),
    Mapping("skillbridge_eligibility_date", UNSUPPORTED, "Military SkillBridge-specific date field, no capability.", True),

    # --- EEO.
    Mapping("eeo_gender_identity", "eeo_gender", "Same fact; resolveValue's case is named 'eeo_gender'.", True),
    Mapping("eeo_race_ethnicity", "eeo_race", "Same fact; resolveValue's case is named 'eeo_race'.", True),
    Mapping("eeo_hispanic_latino", "eeo_hispanic", "Same fact; resolveValue's case is named 'eeo_hispanic'.", True),
    Mapping("eeo_veteran_status", "eeo_veteran", "Same fact; resolveValue's case is named 'eeo_veteran'.", True),
    Mapping("eeo_disability_status", "eeo_disability", "Same fact; resolveValue's case is named 'eeo_disability'.", True),
    Mapping("eeo_sexual_orientation", UNSUPPORTED, "No capability/profile field for sexual orientation exists (distinct from gender/race/hispanic/veteran/disability, which do).", True),
    Mapping("eeo_transgender", UNSUPPORTED, "No separate transgender-status capability exists.", True),
    Mapping("eeo_generic_decline_option", UNSUPPORTED, "Not a fact to resolve — a decline/prefer-not-to-answer OPTION that exists as synonyms (DECLINE_SYNONYMS) attached to other EEO cases, not a category of its own.", True),

    # --- Education.
    Mapping("education_school", "school", "Same fact; resolveValue's case is named 'school'.", True),
    Mapping("education_degree", "degree", "Same fact; resolveValue's case is named 'degree'.", True),
    Mapping("education_discipline", "major", "Same fact; resolveValue's case is named 'major'.", True),
    Mapping("field_of_study_relevance", UNSUPPORTED, "Free-text 'is your degree relevant to this role' explanation, not a simple profile-fact lookup — closer to essay/custom_answers territory than a resolveValue case.", False),
    Mapping("education_end_date", "graduation_date", "Same underlying fact — resolveValue's 'graduation_date' case is the end date of the most recent/current program.", True),
    Mapping("graduation_date", "graduation_date", "Ontology has BOTH 'graduation_date' and 'education_end_date' as separate TOPIC_CATEGORIES entries for what is the same real-world fact (confirmed by reading both categories' likely usage — no distinguishing description exists for either in taxonomy_v1.py). Both map to the same single resolveValue capability.", False),
    Mapping("education_start_date", UNSUPPORTED, "No program-start-date capability exists (only graduation/end date).", True),
    Mapping("academic_grade", "gpa", "Same fact; resolveValue's case is named 'gpa'.", True),
    Mapping("standardized_test_score", UNSUPPORTED, "No SAT/GRE/test-score capability exists.", True),
    Mapping("currently_enrolled_status", UNSUPPORTED, "No 'are you currently enrolled' boolean capability exists separately from graduation_date.", True),
    Mapping("current_school_year", UNSUPPORTED, "No freshman/sophomore/etc. class-year capability exists.", True),
    Mapping("courses_remaining", UNSUPPORTED, "No capability for this.", True),
    Mapping("certifications", UNSUPPORTED, "No certifications-list capability exists.", True),

    # --- Job specifics / experience.
    Mapping("salary_expectation", "compensation", "Same fact; resolveValue's case is named 'compensation' and does live JD-range parsing + profile midpoint fallback.", True),
    Mapping("compensation_range_acknowledgment", UNSUPPORTED, "A yes/no 'do you acknowledge the posted range' checkbox, distinct from stating a salary expectation — no dedicated capability.", True),
    Mapping("current_salary", UNSUPPORTED, "Distinct fact from desired/expected compensation; no capability resolves current salary specifically.", True),
    Mapping("current_benefits", UNSUPPORTED, "No capability for this.", True),
    Mapping("competing_offers_disclosure", UNSUPPORTED, "No capability for this.", True),
    Mapping("notice_period", UNSUPPORTED, "No capability for current-employer notice period.", True),
    Mapping("contract_length", UNSUPPORTED, "No capability for desired contract length.", True),
    Mapping("employment_type", UNSUPPORTED, "No capability for desired employment type (FT/PT/contract) preference.", True),
    Mapping("workplace_type", UNSUPPORTED, "No capability for remote/hybrid/onsite preference.", True),
    Mapping("availability_start_date", "start_date", "Same underlying fact — resolveValue's 'start_date' case resolves via custom_answers lookup for 'what term were you looking to start'.", True),
    Mapping("availability_end_date", UNSUPPORTED, "No capability for an availability END date (only start_date exists).", True),
    Mapping("availability_days", UNSUPPORTED, "No capability for which days of the week available.", True),
    Mapping("availability_hours_per_week", UNSUPPORTED, "No capability for hours/week availability.", True),
    Mapping("availability_commitment_confirmation", UNSUPPORTED, "A yes/no confirmation, not a fact lookup — no capability.", True),
    Mapping("interview_availability", UNSUPPORTED, "No capability for interview scheduling availability.", True),
    Mapping("travel_willingness", UNSUPPORTED, "No capability for willingness-to-travel percentage/frequency.", True),
    Mapping("willing_to_relocate", UNSUPPORTED, "No capability distinct from location_preference/needs_sponsorship exists for a dedicated relocation-willingness question.", True),
    Mapping("skill_experience_years", "years_experience", "Same underlying fact — resolveValue's 'years_experience' resolves via custom_answers lookup for 'years of experience'.", True),
    Mapping("relevant_industry_experience", UNSUPPORTED, "Free-text/essay-shaped, not a simple fact lookup.", False),
    Mapping("technical_skills", UNSUPPORTED, "No structured skills-list capability exists.", True),
    Mapping("language_proficiency", UNSUPPORTED, "No capability for language proficiency.", True),
    Mapping("qualifications_confirmation", UNSUPPORTED, "A yes/no confirmation checkbox, not a fact lookup.", True),
    Mapping("writing_sample_request", UNSUPPORTED, "File-upload/essay request, no dedicated capability (distinct from cover_letter/transcript uploads that DO exist).", True),
    Mapping("publication_list", UNSUPPORTED, "No capability for this.", True),
    Mapping("current_job_title", UNSUPPORTED, "No current-job-title capability exists in the live profile schema.", True),
    Mapping("current_company", UNSUPPORTED, "No current-employer capability distinct from previously_employed_here's prior-employers list.", True),
    Mapping("currently_employed_elsewhere", UNSUPPORTED, "No capability for this.", True),
    Mapping("current_employee_of_company", "previously_employed_here", "Close but not confirmed identical — resolveValue's 'previously_employed' checks prevEmployers against the TARGET company's name (was I EVER employed here), which may not be the same question as 'are you a CURRENT employee' depending on exact phrasing. Provisional mapping, needs a side-by-side corpus check.", False),
    Mapping("previously_employed_here", "previously_employed", "Same fact; resolveValue's case is named 'previously_employed'.", True),
    Mapping("previously_applied_here", UNSUPPORTED, "Distinct fact from previously_employed_here (applied vs. worked) — no capability.", True),
    Mapping("employee_referral", "referral", "Same fact; resolveValue's case is named 'referral', resolves via custom_answers lookup.", True),
    Mapping("how_heard_about_role", UNSUPPORTED, "Distinct from employee_referral (referral is a specific person; this is the broader 'where did you hear about us' channel question) — no dedicated capability, though QUESTION_ALIASES normalizes phrasing toward 'where did you hear about', it still resolves through the same referral/custom_answers path with no guarantee of a good answer for the channel-not-person case.", False),
    Mapping("cover_letter_upload", "cover_letter", "Same underlying fact; resolveValue's 'cover_letter' case only fills free-text variants (file-upload cover letter is explicitly skipped per its own comment) — capability exists but is narrower than the ontology category's full scope.", True),
    Mapping("resume_upload", UNSUPPORTED, "Resume upload is handled by ATS-adapter lifecycle code (content/greenhouse.js 'resume-upload-first'), not resolveValue — out of this mapping's scope, not a gap.", True),

    # --- Consent / disclosures / compliance.
    Mapping("consent_attestation_general", UNSUPPORTED, "General attestation checkboxes are handled by the standing 'auto-check consent/background-check boxes' rule (FORM_ENGINE_DESIGN.md §1.6), which is an ACTION not a resolveValue capability lookup.", True),
    Mapping("consent_background_check", UNSUPPORTED, "Same as consent_attestation_general — auto-check action, not a resolveValue lookup.", True),
    Mapping("consent_ccpa_share_sale", UNSUPPORTED, "Same auto-check-action shape.", True),
    Mapping("consent_sms_communication", UNSUPPORTED, "Same auto-check-action shape.", True),
    Mapping("ccpa_california_disclosure", UNSUPPORTED, "Same auto-check-action shape.", True),
    Mapping("criminal_background_disclosure", UNSUPPORTED, "No profile field for criminal history; typically a yes/no with no reliable default — do not auto-answer.", True),
    Mapping("nepotism_disclosure", UNSUPPORTED, "No profile field for family-employed-here disclosure.", True),
    Mapping("pep_disclosure", UNSUPPORTED, "Politically-exposed-person disclosure, no profile field.", True),
    Mapping("marketing_communications_optin", UNSUPPORTED, "Same auto-check-action shape as other consent categories, but opt-IN (not required) — likely wants a deliberate default (probably decline), not yet decided.", True),
    Mapping("age_18_or_older", UNSUPPORTED, "No age/DOB capability exists in the live profile schema.", True),

    # --- Location / department preference, work history.
    Mapping("location_preference", UNSUPPORTED, "No capability for 'which office/location would you prefer' distinct from current location_city/state.", True),
    Mapping("department_interest", UNSUPPORTED, "No capability — also the category with the documented false-merge history (corpus_analysis/README.md), treat any resolved instance with extra suspicion.", True),
    Mapping("work_history_employer", UNSUPPORTED, "No structured work-history capability beyond the single previous_employers[] list used for previously_employed matching.", True),
    Mapping("work_history_title", UNSUPPORTED, "Same gap.", True),
    Mapping("work_history_start_date", UNSUPPORTED, "Same gap.", True),
    Mapping("work_history_end_date", UNSUPPORTED, "Same gap.", True),

    # --- Military.
    Mapping("military_branch", UNSUPPORTED, "No capability.", True),
    Mapping("military_rank", UNSUPPORTED, "No capability.", True),
    Mapping("military_specialty_code", UNSUPPORTED, "No capability.", True),
    Mapping("military_time_in_service", UNSUPPORTED, "No capability.", True),
    Mapping("military_separation_date", UNSUPPORTED, "No capability.", True),

    # --- Misc / long-tail.
    Mapping("essay", UNSUPPORTED, "Explicitly deferred to the LLM fallback layer (FORM_ENGINE_DESIGN.md §3.6, 'LLM FALLBACK... gated: low confidence / ESSAY / unknown'), not a resolveValue capability by design.", True),
    Mapping("attention_check", UNSUPPORTED, "Anti-bot/attention-check questions require reading and matching specific instructed text per-instance, not a profile lookup.", True),
    Mapping("agency_preference", UNSUPPORTED, "No capability.", True),
    Mapping("competition_participation", UNSUPPORTED, "No capability.", True),
    Mapping("event_attendance", UNSUPPORTED, "No capability.", True),
    Mapping("internship_agreement_confirmation", UNSUPPORTED, "A yes/no confirmation, not a fact lookup.", True),
    Mapping("preferred_contact_method", UNSUPPORTED, "No capability for email-vs-phone contact preference.", True),
    Mapping("program_affiliation", UNSUPPORTED, "No capability.", True),
    Mapping("scholarship_program_affiliation", UNSUPPORTED, "No capability.", True),
    Mapping("student_org_involvement", UNSUPPORTED, "No capability.", True),
    Mapping("ai_tool_usage_disclosure", UNSUPPORTED, "No capability — genuinely job-posting-specific skill-gate phrasing per the held-out validation's characterization of the residual gap.", True),
]

# --- PROPOSED_V2_ADDITIONS from taxonomy_v1.py — mapped separately since
# they were added AFTER the original 118, not yet formally merged into
# TOPIC_CATEGORIES.
_MAPPINGS += [
    Mapping("consent_privacy_policy", UNSUPPORTED, "Same auto-check-action shape as other consent categories.", True),
    Mapping("consent_gdpr_notice", UNSUPPORTED, "Same auto-check-action shape as other consent categories.", True),
    # visa_type already mapped above (it's also listed in TOPIC_CATEGORIES's
    # docstring context) — not duplicated here.
]

MAPPING = {m.ontology: m for m in _MAPPINGS}


def capability_for(ontology_category: str) -> Optional[str]:
    """Returns the resolveValue capability name for an ontology category,
    or None if the category isn't in the mapping at all (distinct from
    UNSUPPORTED, which means "looked at it, no capability exists yet").
    """
    m = MAPPING.get(ontology_category)
    if m is None or m.capability == UNSUPPORTED:
        return None
    return m.capability
