"""Batch 5 (final batch) decisions — every remaining residue field read
individually, chunk-by-chunk with founder confirmation in chat before
recording. This is the last batch; after this the corpus's needs_review
pile should be empty (only the auto-matched/pre-confirmed residue remains
as tracked, resolved data).
"""

import json

with open("scratchpad/oc_compact_full.json", encoding="utf-8") as f:
    data = json.load(f)


def ci_of(name):
    return next(i for i, c in enumerate(data) if c["company"] == name)


CI = {name: ci_of(name) for name in [
    "spacex", "spire", "stripe", "stokespacetechnologies", "studsinc",
    "teads1", "towerresearchcapital", "traderepublic", "vardaspace", "vast",
    "verkada", "veterinaryemergencygroupst", "woolpert", "workato", "zscaler",
]}

ENTRIES = []


def reject(company, fi, note):
    ENTRIES.append({"ci": CI[company], "fi": fi, "action": "reject", "category": None, "note": note})


def confirm(company, fi, category, note=""):
    ENTRIES.append({"ci": CI[company], "fi": fi, "action": "confirm", "category": category, "note": note})


# --- Chunk 1: spacex remainder, spire, stripe (full filter widget) ---
confirm("spacex", 54, "other_followup", "'Other Student Group(s)' — follow-up to the student-groups question.")
confirm("spacex", 55, "previously_employed_here", "'SpaceX, xAI & X Employment History'.")
confirm("spacex", 65, "consent_attestation_general", "'Can you perform all essential functions with or without reasonable accommodations?' — ADA-related attestation.")
confirm("spacex", 72, "location_preference", "Section-fallback 'Preferred Internship Location(s)'.")
confirm("spacex", 73, "student_org_involvement", "Section-fallback 'Are you a member of any of the following student groups?'")
reject("spire", 3, "section='Strictly Necessary Cookies', label='Always Active' — cookie-consent banner.")
reject("spire", 7, "id='storage-access-group' — cookie-consent banner toggle.")
reject("stripe", 0, "name='jobsQueryInput', placeholder='Search for a job' — job-board search box.")
_STRIPE_FILTER_NOTE = "Confirmed via raw HTML (corpus/pages/7236933.html.gz): class='ControlledFilterSelect', id='jobsTeamsFilter-list', header 'Teams' — same job-board filter widget already confirmed fake for this company's Marketing/Finance/Sales/etc. fields."
_stripe_fis = [1, 3, 4, 5, 6, 7, 8, 10, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 25, 27, 28, 29, 30, 32, 33,
               34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58,
               59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 80, 81, 82, 83, 84,
               85, 86, 87, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108,
               110, 111, 112, 113, 114, 115, 116, 117, 118, 121, 123]
for fi in _stripe_fis:
    reject("stripe", fi, _STRIPE_FILTER_NOTE)

# --- Chunk 2: stokespacetechnologies, studsinc ---
confirm("stokespacetechnologies", 16, "work_authorized")
confirm("stokespacetechnologies", 18, "needs_sponsorship")
confirm("stokespacetechnologies", 20, "location_city", "Combined city/state/ZIP field.")
confirm("stokespacetechnologies", 22, "availability_commitment_confirmation", "'commit to a Spring internship from January - April 2027'.")
confirm("stokespacetechnologies", 24, "academic_grade")
confirm("stokespacetechnologies", 26, "department_interest", "'Team Preference (select #1 choice)'.")
confirm("stokespacetechnologies", 28, "department_interest", "'Team Preference (select #2 choice)' — ranked alternative, same category.")
confirm("stokespacetechnologies", 30, "essay", "'What motivates you?'")
confirm("stokespacetechnologies", 31, "essay", "Skills-learned-outside-classroom open-ended question.")
confirm("stokespacetechnologies", 33, "how_heard_about_role", "Combines how-heard + referral name; leaning toward the primary ask.")
confirm("studsinc", 7, "age_18_or_older")
confirm("studsinc", 9, "travel_willingness", "'willing and able to travel to a Studs Flagship location for 6 weeks of training'.")
confirm("studsinc", 11, "essay", "'Why did you choose to apply to Studs' apprenticeship program?'")
confirm("studsinc", 12, "previously_employed_here", "Combines current+past employment; leaning toward the broader concept.")
confirm("studsinc", 14, "location_city")
confirm("studsinc", 15, "employment_type", "'Part Time position or a Full Time position'.")
confirm("studsinc", 17, "availability_hours_per_week")
confirm("studsinc", 18, "availability_days", "New category. 'Which days of the week are you available to work?' — distinct from hours-per-week.")
confirm("studsinc", 19, "consent_attestation_general", "Bloodborne-pathogen occupational-exposure acknowledgment.")
confirm("studsinc", 21, "consent_attestation_general", "ADA-related job-duties acknowledgment.")
confirm("studsinc", 30, "location_preference", "Section-fallback studio-location preference.")

# --- Chunk 3: teads1, towerresearchcapital, traderepublic ---
confirm("teads1", 9, "needs_sponsorship")
confirm("teads1", 11, "employment_type", "'What type of contract are you looking for?'")
confirm("teads1", 13, "contract_length", "'What is the duration?'")
confirm("teads1", 15, "education_degree")
confirm("teads1", 17, "language_proficiency")
confirm("teads1", 19, "marketing_communications_optin", "'happy for Teads to contact me about future job opportunities'.")
confirm("teads1", 21, "consent_attestation_general")
confirm("towerresearchcapital", 25, "pep_disclosure", "New category. 'Are you or have you been entrusted with a position or function in any government, international organization... or state-owned enterprise?' — politically-exposed-person (PEP) regulatory disclosure.")
confirm("towerresearchcapital", 27, "pep_disclosure", "'immediate family member of someone holding such a position' — extension of the PEP disclosure.")
confirm("towerresearchcapital", 29, "previously_employed_here")
confirm("towerresearchcapital", 31, "employee_referral")
confirm("traderepublic", 4, "availability_start_date", "Verified via raw HTML: placeholder='Are you available and in Berlin between 15 July and 15 Oct 2026?' — real question hidden in placeholder text, label field was empty (extraction gap, same pattern as Anduril's 'Type here').")
confirm("traderepublic", 5, "essay", "Verified via raw HTML: placeholder='Are you proficient in Microsoft Excel and experienced in using AI tools to optimize your workflow?' — skills self-assessment, open response.")
confirm("traderepublic", 6, "essay", "Verified via raw HTML: placeholder='Do you have a solid academic or practical background in taxation or experience with Tax Technology tools?'")
confirm("traderepublic", 7, "language_proficiency", "Verified via raw HTML: placeholder='What is your comfort level with German language?'")
confirm("traderepublic", 11, "eeo_gender_identity", "'What is your gender identity?'")
confirm("traderepublic", 12, "cover_letter_upload")

# --- Chunk 4: vardaspace, vast, verkada ---
confirm("vardaspace", 9, "citizenship_status", "ITAR-specific U.S. citizen/lawful-permanent-resident/protected-individual eligibility check.")
confirm("vardaspace", 11, "availability_start_date", "'seeking a Fall internship'.")
confirm("vardaspace", 15, "workplace_type", "Full-time on-site at El Segundo, CA.")
confirm("vardaspace", 17, "needs_sponsorship")
reject("vast", 0, "Empty search box — job-board search.")
reject("vast", 2, "'Office' (id='offices', select) — job-board office-filter, same pattern as opswat's officeId.")
confirm("verkada", 12, "academic_grade", "'current GPA'.")
confirm("verkada", 13, "workplace_type", "Onsite HQ commute/relocate question.")
confirm("verkada", 15, "availability_commitment_confirmation", "Specific weekday/hours schedule commitment, same family as studsinc's schedule questions.")

# --- Chunk 5: veterinaryemergencygroupst, woolpert ---
_VEG_NOTE = "Confirmed via raw HTML: Wix site-builder page (comp-* id naming convention), same job-board filter widget family as JOB TYPE/STATE-PROVINCE fields on this page — no real form content found near these ids."
reject("veterinaryemergencygroupst", 0, _VEG_NOTE)
reject("veterinaryemergencygroupst", 1, "'JOB TYPE' — Wix job-board filter widget.")
reject("veterinaryemergencygroupst", 2, "'STATE / PROVINCE' — Wix job-board filter widget.")
reject("veterinaryemergencygroupst", 4, _VEG_NOTE + " label='1' has no real readable content.")
reject("veterinaryemergencygroupst", 6, "'Non-Essential Cookies' — cookie-consent banner.")
reject("veterinaryemergencygroupst", 7, "Section-fallback 'Manage Cookie Preferences' — cookie-consent banner.")
confirm("woolpert", 26, "work_authorized")
confirm("woolpert", 30, "education_degree", "'highest level of education you've completed'.")
confirm("woolpert", 32, "availability_start_date")
confirm("woolpert", 33, "location_city", "'current location'.")
confirm("woolpert", 36, "essay", "'Can you tell me a little bit about yourself?'")
confirm("woolpert", 37, "essay", "'What are you studying, and how did you choose that major?'")
confirm("woolpert", 38, "essay", "'How does this internship align with your career goals?'")
confirm("woolpert", 39, "essay", "Software/tools familiarity, open-ended.")
confirm("woolpert", 41, "competing_offers_disclosure", "'Are you in any other interview processes at the moment?' — same category as the offers/deadlines disclosure (competing-process concept).")
confirm("woolpert", 48, "consent_attestation_general", "Section-fallback 'Privacy Acknowledgement'.")

# --- Chunk 6 (final): workato, zscaler ---
confirm("workato", 0, "email", "name='email', placeholder='Enter email' — real field, label missing (same extraction gap as other placeholder-only fields found this session).")
_WORKATO_UTM_NOTE = "Marketing-attribution/analytics tracking parameter (UTM source/medium/campaign/content/term, reference value, GA client id) — not user-facing."
for fi in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]:
    reject("workato", fi, _WORKATO_UTM_NOTE)
reject("workato", 14, "section='Sound Exciting?', placeholder='Find a role' — job-board search box.")
confirm("zscaler", 13, "other_followup", "'If you selected Other please tell us how you learned about this job.'")
confirm("zscaler", 14, "work_authorized")
confirm("zscaler", 16, "needs_sponsorship")
confirm("zscaler", 18, "other_followup", "'If yes, please advise what support is needed:'")
confirm("zscaler", 19, "currently_enrolled_status")
confirm("zscaler", 21, "education_discipline", "'What is your major?'")
confirm("zscaler", 22, "graduation_date", "Expected graduation month.")
confirm("zscaler", 23, "graduation_date", "Expected graduation year — paired field, same category.")
confirm("zscaler", 24, "technical_skills", "New category. 'In which coding languages are you proficient?' — defined checklist-style technical-skill self-report, distinct from open-ended essay.")
confirm("zscaler", 26, "department_interest", "'Which area(s) are you interested in pursuing?'")
confirm("zscaler", 28, "other_followup", "'If you selected Other to the preceding question...'")
confirm("zscaler", 29, "previously_employed_here")
confirm("zscaler", 31, "pep_disclosure", "'procurement or contract award activities involving Zscaler as a government employee or official' — same PEP/conflict-of-interest family as Tower Research's question.")
confirm("zscaler", 33, "military_time_in_service", "'at least six months remaining on active duty, national guard or reserves' — same category as MKS2 Technologies' military_time_in_service.")
confirm("zscaler", 35, "mailing_address", "'Home Address'.")
confirm("zscaler", 36, "eeo_gender_identity", "section='Voluntary Self Identification', 'Sex*'.")
confirm("zscaler", 39, "consent_attestation_general", "Section-fallback 'Zscaler Confidential Information'.")
confirm("zscaler", 40, "consent_attestation_general", "Section-fallback 'Zscaler Privacy Policy'.")

with open("scratchpad/batch5_decisions.json", "w", encoding="utf-8") as f:
    json.dump(ENTRIES, f, indent=2)

rej = sum(1 for e in ENTRIES if e["action"] == "reject")
conf = sum(1 for e in ENTRIES if e["action"] == "confirm")
print(f"total entries: {len(ENTRIES)} (reject: {rej}, confirm: {conf})")

new_cats = sorted(set(e["category"] for e in ENTRIES if e["action"] == "confirm"))
print(f"\ncategories touched ({len(new_cats)}):")
for c in new_cats:
    print(" ", c)
