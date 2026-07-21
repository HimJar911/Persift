"""Batch 4 decisions — read field-by-field in chat, chunk by chunk, with
the founder confirming each chunk before moving to the next. This script
only records what was already read and agreed; no field was classified by
pattern-matching in code.

Opens with corrections for andurilindustries fi=10,11 and d2l's remaining
filter-widget fields (fi=3,13-24) — discussed in an earlier turn but never
actually written to the pipeline, caught when they resurfaced in this
batch's residue dump.
"""

import json

with open("scratchpad/oc_compact_full.json", encoding="utf-8") as f:
    data = json.load(f)


def ci_of(name):
    return next(i for i, c in enumerate(data) if c["company"] == name)


CI = {name: ci_of(name) for name in [
    "andurilindustries", "d2l", "ogilvy", "omnicomhealth", "oneacrefund",
    "opswat", "panthalassa", "pathai", "pindrop", "pinterestcareers",
    "point72", "powerdigitalmarketing", "presidents", "psiquantum",
    "recursionpharmaceuticals", "redventures", "rocketlab", "safariai",
    "samsungresearchamericainternship", "scaleai", "scandit", "scopely",
    "senrasystems", "sentinellabs", "sesai", "sharkninjaoperatingllc",
    "shift5", "silananotechnologies", "skildai-careers", "spacex",
]}

ENTRIES = []


def reject(company, fi, note):
    ENTRIES.append({"ci": CI[company], "fi": fi, "action": "reject", "category": None, "note": note})


def confirm(company, fi, category, note=""):
    ENTRIES.append({"ci": CI[company], "fi": fi, "action": "confirm", "category": category, "note": note})


# --- CORRECTIONS: discussed in an earlier turn, never written ---
confirm("andurilindustries", 10, "resume_upload", "<label>Resume</label>, type=file — real application field.")
confirm("andurilindustries", 11, "department_interest", "Combobox version of 'Which type of role are you interested in?' — same 9 options (Design/Engineering/Finance/Marketing/Operations/People/Product/Sales/University) as the already-confirmed checkbox version at fi 122-130.")
reject("d2l", 3, "Same name='filter-group-1_N' job-board filter widget already confirmed fake for this company.")
_D2L_LOC_NOTE = "Same filter-group-1_N job-board location-filter widget already confirmed fake for this company's department options."
for fi in [13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 24]:
    reject("d2l", fi, _D2L_LOC_NOTE)

# --- Chunk 1: ogilvy fi 12-45 ---
_OG_CRM_NOTE = "Hidden Drupal Webform-to-CRM plumbing field (field_source_group_c, field_campaign_id, field_assigned_user_id, field_redirect_url, etc.) — marketing-automation config, not user-facing."
for fi in [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]:
    reject("ogilvy", fi, _OG_CRM_NOTE)
reject("ogilvy", 25, "Submit button (id='edit-send'), not a question.")
_OG_CONTACT_NOTE = "Part of Ogilvy's general 'Contact Us'/talent-network form (verified: has contact_email + Interest dropdown with Employment Verification/Media Inquiries/New Business options) — not tied to a specific job application."
for fi in [30, 31, 32, 33, 34, 35]:
    reject("ogilvy", fi, _OG_CONTACT_NOTE)
_OG_AOI_NOTE = "Verified via raw HTML: name='area_of_interest[...]', sits inside the same general Contact-Us form as fi 30-35, not a job-specific department question."
for fi in [40, 42, 43]:
    reject("ogilvy", fi, _OG_AOI_NOTE)
reject("ogilvy", 44, "'Necessary cookies' — cookie-consent banner.")
reject("ogilvy", 45, "'Drop-Down Menu' (id='menu-toggle') — site nav menu toggle, page chrome.")

# --- Chunk 2: omnicomhealth, oneacrefund ---
confirm("omnicomhealth", 3, "agency_preference", "New category. Verified Greenhouse custom field (id='custom-field-7329304008', section='A healthy career starts here') — media-holding-company concept (which agency within the network), same real pattern as this company's already-confirmed Department field.")
confirm("omnicomhealth", 5, "location_preference", "Verified Greenhouse custom field (id='custom-field-6375233008').")
reject("oneacrefund", 0, "'E-mail', section='Join our careers mailing list' — newsletter signup, not the application form.")
_OAF_NAV_NOTE = "Verified via raw HTML: class='c-header-menu__item-link' — literally the site's main navigation menu (dropdown of country career pages), not form checkboxes at all."
for fi in [4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15, 16]:
    reject("oneacrefund", fi, _OAF_NAV_NOTE)
_OAF_FILTER_NOTE = "Verified via raw HTML: class='c-filter__item', name='field_career_level_target_id[...]' — same job-board filter widget already confirmed fake for this company's location fields."
for fi in [18, 19, 20]:
    reject("oneacrefund", fi, _OAF_FILTER_NOTE)

# --- Chunk 3: opswat, panthalassa ---
reject("opswat", 2, "itype=search, id='jobTitle', placeholder='Job Title' — job-board search box.")
reject("opswat", 3, "name='officeId', options include 'All Locations' + dozens of cities/countries — office-location filter dropdown, job-board chrome.")
reject("opswat", 5, "name='q', placeholder='Keyword...' — second search box, same job-board chrome family as fi=2.")
confirm("panthalassa", 20, "location_city", "'Where are you currently located?'")
confirm("panthalassa", 21, "workplace_type", "'full-time on-site at our Portland, Oregon offices, or... only seeking remote opportunities'.")
confirm("panthalassa", 25, "employee_referral")
confirm("panthalassa", 26, "linkedin_url")
confirm("panthalassa", 27, "personal_website")
confirm("panthalassa", 28, "essay", "'What else would you like to tell us about yourself or your application? (optional)'")
confirm("panthalassa", 30, "department_interest", "Section-fallback 'specify your area of expertise and any other areas you are interested in'.")

# --- Chunk 4: pathai, pindrop, pinterestcareers ---
confirm("pathai", 20, "preferred_pronouns", "'Preferred name & pronouns:' combines two concepts; pronouns is the more specific/actionable half.")
confirm("pathai", 21, "nepotism_disclosure")
confirm("pathai", 23, "other_followup", "'If you do have any relatives currently employed by PathAI, please list them here'.")
confirm("pathai", 24, "employee_referral")
confirm("pathai", 27, "needs_sponsorship")
confirm("pathai", 34, "availability_start_date", "Section-fallback 'For which term are you looking for an internship?'")
confirm("pindrop", 5, "consent_attestation_general", "'Required Acknowledgment *'")
reject("pinterestcareers", 0, "'Keywords:' search box — job-board search.")
reject("pinterestcareers", 1, "'Location:' select — job-board filter.")
reject("pinterestcareers", 9, "'Remote work only', section='Filter jobs'.")
reject("pinterestcareers", 10, "Empty checkbox_group, section='Filter jobs' — same filter section as fi=9.")

# --- Chunk 5: point72 ---
confirm("point72", 22, "academic_grade", "'current cumulative GPA'.")
confirm("point72", 24, "academic_grade", "'GPA scale at your institution' — context needed to interpret the GPA answer, same category.")
confirm("point72", 26, "standardized_test_score", "New category. 'SAT or ACT score' — distinct from academic_grade since it's a different metric shape.")
confirm("point72", 28, "how_heard_about_role")
confirm("point72", 30, "previously_applied_here", "New category. 'Have you previously applied to work at Point72?' — distinct from previously_employed_here.")
confirm("point72", 32, "other_followup", "'provide the date(s) and role(s) to which you have applied'.")
confirm("point72", 33, "needs_sponsorship", "Japan-specific visa sponsorship.")
confirm("point72", 35, "language_proficiency")
confirm("point72", 36, "graduation_date", "'Will you graduate between December 2027 and July 2028?'")
confirm("point72", 38, "availability_start_date", "'available to intern in person between June and August 2027'.")
confirm("point72", 40, "essay")
confirm("point72", 41, "essay")
confirm("point72", 42, "location_preference", "Region-specific application-routing confirmation (Japan office).")
confirm("point72", 43, "consent_attestation_general", "'Privacy *'")
confirm("point72", 45, "eeo_gender_identity", "section='Diversity', 'I identify as'.")
confirm("point72", 46, "eeo_hispanic_latino")
confirm("point72", 47, "eeo_race_ethnicity", "'Ethnicity/Race'.")
confirm("point72", 49, "language_proficiency", "Section-fallback 'written Japanese proficiency'.")
confirm("point72", 50, "language_proficiency", "Section-fallback 'spoken Japanese proficiency'.")

# --- Chunk 6: powerdigitalmarketing, presidents, psiquantum ---
confirm("powerdigitalmarketing", 25, "personal_website")
confirm("powerdigitalmarketing", 26, "workplace_type", "'comfortable working in a remote setting'.")
confirm("powerdigitalmarketing", 28, "currently_enrolled_status")
confirm("powerdigitalmarketing", 30, "consent_attestation_general", "Unpaid-internship/course-credit-approval acknowledgment.")
confirm("powerdigitalmarketing", 32, "previously_applied_here", "'interviewed with Power Digital in the past 3 years'.")
confirm("powerdigitalmarketing", 34, "availability_start_date", "'able to intern with us from September to December 2026'.")
confirm("powerdigitalmarketing", 36, "ai_tool_usage_disclosure", "New category. 'Have you used AI tools (ChatGPT, Gemini, Perplexity...) to assist with tasks like research, writing, or automation?'")
confirm("presidents", 8, "nationality_check", "'Are you native Danish?'")
confirm("presidents", 10, "currently_enrolled_status", "'Are you currently studying?'")
confirm("presidents", 13, "linkedin_url")
confirm("psiquantum", 14, "currently_enrolled_status", "'Do you have a Ph.D. or currently enrolled in a Ph.D. program?'")
confirm("psiquantum", 16, "name_pronunciation", "New category. 'Phonetic pronunciation of your name'.")
confirm("psiquantum", 20, "work_authorized")
confirm("psiquantum", 22, "nepotism_disclosure", "'friends or relatives with any current employees'.")
confirm("psiquantum", 25, "attention_check", "New category. 'Please include the word \"purple\" in the cover letter submitted.' — classic instruction-following screening trick.")

# --- Chunk 7: recursionpharmaceuticals, redventures ---
confirm("recursionpharmaceuticals", 9, "other_followup", "'If you selected Other in the textbox above, please specify which internship discipline'.")
confirm("recursionpharmaceuticals", 11, "essay", "'What specifically appeals to you about Recursion, and why do you feel drawn to be a part of it?'")
confirm("recursionpharmaceuticals", 12, "eeo_race_ethnicity", "section='Equal Opportunity Employment Information', 'I identify my ethnicity as:'")
confirm("recursionpharmaceuticals", 14, "eeo_gender_identity", "'I identify my gender as:'")
confirm("recursionpharmaceuticals", 16, "eeo_transgender", "'I identify as transgender:'")
confirm("recursionpharmaceuticals", 18, "eeo_sexual_orientation", "'I identify my sexual orientation as:'")
confirm("recursionpharmaceuticals", 22, "eeo_disability_status", "'I have a physical disability'.")
confirm("recursionpharmaceuticals", 25, "department_interest", "Section-fallback 'which internship(s) disciplines you're most interested in'.")
confirm("redventures", 22, "graduation_date")
confirm("redventures", 24, "academic_grade", "'What is your GPA? (to the nearest tenth)'")
confirm("redventures", 26, "workplace_type", "Full-time hybrid-onboarding-cohort acknowledgment.")
confirm("redventures", 30, "other_followup", "'If you heard about us at a career fair... please specify which event'.")
confirm("redventures", 31, "state", "'State of Residence*'")
confirm("redventures", 33, "zip_code", "'Zip / Postal'.")
confirm("redventures", 34, "previously_employed_here")

# --- Chunk 8: rocketlab ---
confirm("rocketlab", 9, "academic_grade", "'Undergrad GPA'.")
confirm("rocketlab", 11, "academic_grade", "'Masters GPA'.")
confirm("rocketlab", 13, "academic_grade", "'Doctorate GPA'.")
confirm("rocketlab", 15, "graduation_date", "'anticipated bachelor's degree graduation date'.")
confirm("rocketlab", 17, "graduation_date", "'anticipated master's degree graduation date'.")
confirm("rocketlab", 19, "qualifications_confirmation", "New category. 'Do you meet all the essential qualifications... under You'll Bring These Qualifications?' — self-assessed role-fit, distinct from a generic attestation.")
confirm("rocketlab", 21, "essay", "'what amount of software engineering experience do you have?...' open-ended.")
confirm("rocketlab", 23, "student_org_involvement", "New category. 'Engineering Organization Involvement: ... active participant in any of the following engineering student groups or competitions'.")
confirm("rocketlab", 25, "other_followup", "'Other Engineering Organization Involvement:'")
confirm("rocketlab", 26, "availability_start_date", "'Preferred Internship/Co-Op Start Date'.")
confirm("rocketlab", 28, "contract_length", "'Preferred Internship/Co-Op Duration... consecutive weeks'.")
confirm("rocketlab", 33, "previously_applied_here", "'Have you previously interviewed at Rocket Lab?'")
confirm("rocketlab", 35, "workplace_type", "'Are you willing to work onsite?'")
confirm("rocketlab", 39, "other_followup", "'If Citizenship Status Other, please explain:'")
confirm("rocketlab", 40, "consent_background_check", "Criminal background check / drug screen / reference check consent.")
confirm("rocketlab", 48, "scholarship_program_affiliation", "New category. Section-fallback 'Are you a participant of the following scholarship, fellowships, or initiatives we support?'")
confirm("rocketlab", 49, "security_clearance", "Section-fallback 'Active Security Clearance(s)'.")

# --- Chunk 9: safariai, samsungresearchamericainternship ---
confirm("safariai", 17, "availability_start_date", "'Can you start by end of Apr, 2026?'")
confirm("safariai", 19, "availability_commitment_confirmation", "'Can you commit 6 months intern?'")
confirm("safariai", 21, "currently_enrolled_status", "'Are you still in school or graduated?'")
confirm("safariai", 23, "location_city", "'Where do you live?'")
confirm("safariai", 24, "currently_employed_elsewhere", "New category. 'Are you currently working in a full time position?' — asks about employment at a DIFFERENT (unspecified) employer, distinct from current_employee_of_company (which asks specifically about the hiring company).")
confirm("safariai", 26, "needs_sponsorship")
confirm("safariai", 28, "work_authorized")
confirm("safariai", 31, "github_url")
confirm("samsungresearchamericainternship", 17, "other_followup", "'Please specify details from your answer above (job board name, employee referrer's name, etc.)'")
confirm("samsungresearchamericainternship", 18, "ccpa_california_disclosure", "New category. 'Additional Information for California Residents:' — distinct from the generic consent_ccpa_share_sale checkbox, this is a disclosure-notice acknowledgment.")
confirm("samsungresearchamericainternship", 22, "needs_sponsorship")
confirm("samsungresearchamericainternship", 24, "education_degree", "'Degree Status - highest degree received or in progress'.")
confirm("samsungresearchamericainternship", 31, "availability_start_date", "Section-fallback 'target internship dates'.")

# --- Chunk 10: scaleai, scandit, scopely, senrasystems ---
confirm("scaleai", 11, "needs_sponsorship")
confirm("scaleai", 14, "other_followup", "'If you selected Other for competition experience, please list it here'.")
confirm("scaleai", 15, "availability_commitment_confirmation", "'Please confirm if you will be available to start' at the stated Jan 2026 date.")
confirm("scaleai", 16, "employee_referral")
confirm("scaleai", 22, "competition_participation", "New category. Section-fallback 'Please select any competitions you have participated in below.'")
confirm("scandit", 15, "workplace_type", "'able to attend our Tampere office every week... hybrid way of working'.")
reject("scopely", 6, "'Sign me up for company updates' (id='signUpCompanyUpdates') — newsletter signup.")
confirm("senrasystems", 13, "location_city", "'Location (city):'")
confirm("senrasystems", 17, "workplace_type", "Redondo Beach/Orange County commute-timeline question.")
confirm("senrasystems", 19, "compensation_range_acknowledgment", "New category. 'Are you open to the compensation range in the job description?' — acceptance of a STATED range, distinct from salary_expectation (stating your own number).")
confirm("senrasystems", 21, "availability_start_date", "'When is your ideal start date?'")
confirm("senrasystems", 22, "essay", "'Why do you want to work at Senra Systems?'")
confirm("senrasystems", 23, "essay", "'Why do you think you're a great fit for this position?'")
confirm("senrasystems", 24, "essay", "'hands-on experience inspecting electromechanical components?' open-ended.")

# --- Chunk 11: sentinellabs, sesai, sharkninjaoperatingllc ---
confirm("sentinellabs", 11, "consent_attestation_general", "'GDPR*'")
confirm("sesai", 14, "work_authorized", "'authorized to work in China'.")
confirm("sesai", 16, "currently_enrolled_status", "'currently in PhD or have PhD degree'.")
confirm("sesai", 25, "language_proficiency", "Section-fallback 'native-level proficiency in Mandarin and professional-level fluency in English'.")
confirm("sharkninjaoperatingllc", 18, "education_school", "'Which college did you attend?'")
confirm("sharkninjaoperatingllc", 20, "other_followup", "'If you selected other, please specify which one'.")
confirm("sharkninjaoperatingllc", 21, "education_degree", "'What degree level are you currently pursuing, or have you most recently completed?'")
confirm("sharkninjaoperatingllc", 23, "graduation_date")
confirm("sharkninjaoperatingllc", 25, "previously_employed_here")
confirm("sharkninjaoperatingllc", 27, "location_preference", "'Which office are you interested in doing your co-op in?'")
confirm("sharkninjaoperatingllc", 29, "workplace_type", "'able to work onsite at the location specified'.")
confirm("sharkninjaoperatingllc", 31, "essay", "AI/LLM experience open-ended question.")
confirm("sharkninjaoperatingllc", 33, "essay", "Data-visualization-tools experience open-ended question.")
confirm("sharkninjaoperatingllc", 37, "marketing_communications_optin", "New category. Recruitment marketing-email opt-in — distinct from general application-processing consent.")

# --- Chunk 12: shift5, silananotechnologies, skildai-careers, spacex ---
confirm("shift5", 13, "travel_willingness", "New category. 'Are you willing to travel ~50% of the time?'")
confirm("silananotechnologies", 22, "needs_sponsorship")
confirm("silananotechnologies", 26, "availability_start_date", "'available between June-December 2026'.")
confirm("silananotechnologies", 28, "currently_enrolled_status", "'Are you currently a student?'")
confirm("silananotechnologies", 30, "willing_to_relocate", "'able to relocate to the SF Bay Area'.")
confirm("skildai-careers", 14, "essay", "'Why do you want to work at Skild AI?'")
confirm("skildai-careers", 15, "essay", "'Tell us about two to three projects or accomplishments you're most proud of!'")
confirm("spacex", 23, "essay", "'top two exceptional academic and/or professional accomplishments' summary.")
confirm("spacex", 26, "currently_enrolled_status", "'Please select your enrollment status:'")
confirm("spacex", 28, "availability_start_date", "'the month you will be able to start your internship'.")
confirm("spacex", 42, "academic_grade", "'GPA (Undergraduate)'.")
confirm("spacex", 44, "academic_grade", "'GPA (Graduate)'.")
confirm("spacex", 46, "academic_grade", "'GPA (Doctorate)'.")
confirm("spacex", 48, "standardized_test_score", "'SAT Score'.")
confirm("spacex", 50, "standardized_test_score", "'ACT Score'.")
confirm("spacex", 52, "department_interest", "'#1 SpaceX Program Preference'.")

with open("scratchpad/batch4_decisions.json", "w", encoding="utf-8") as f:
    json.dump(ENTRIES, f, indent=2)

rej = sum(1 for e in ENTRIES if e["action"] == "reject")
conf = sum(1 for e in ENTRIES if e["action"] == "confirm")
print(f"total entries: {len(ENTRIES)} (reject: {rej}, confirm: {conf})")

new_cats = sorted(set(e["category"] for e in ENTRIES if e["action"] == "confirm"))
print(f"\ncategories touched ({len(new_cats)}):")
for c in new_cats:
    print(" ", c)
