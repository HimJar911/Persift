"""Batch 2 decisions — every field individually read against real DOM/
context evidence. Companies: acluinternships, ada18, alixpartners, alxafrica,
cypresscreekrenewables(remaining), d2l(remaining), dataiku, debutbiotech25,
defenseunicorns, dvtrading, ensono, everstreamanalytics, feedzai, feverup,
gemini, gensyn, globalrelay, golden-careers, gostudent, groww, guidepoint,
hala, horizonindustrieslimited.

Also fixes a systemic harvester bug: field_id_hash '709446a2' (tag=None,
every attribute null/empty) appears 12x across the corpus — a malformed
trailing extraction artifact, not real DOM content. Rejected globally by
hash, not company-by-company.
"""

import json

with open("scratchpad/oc_compact_full.json", encoding="utf-8") as f:
    data = json.load(f)


def ci_of(name):
    return next(i for i, c in enumerate(data) if c["company"] == name)


CI = {name: ci_of(name) for name in [
    "acluinternships", "ada18", "alixpartners", "alxafrica",
    "cypresscreekrenewables", "d2l", "dataiku", "debutbiotech25",
    "defenseunicorns", "dvtrading", "ensono", "everstreamanalytics",
    "feedzai", "feverup", "gemini", "gensyn", "globalrelay",
    "golden-careers", "gostudent", "groww", "guidepoint", "hala",
    "horizonindustrieslimited",
]}

ENTRIES = []


def reject(company, fi, note):
    ENTRIES.append({"ci": CI[company], "fi": fi, "action": "reject", "category": None, "note": note})


def confirm(company, fi, category, note=""):
    ENTRIES.append({"ci": CI[company], "fi": fi, "action": "confirm", "category": category, "note": note})


# --- Global fix: malformed extraction artifact (tag=None, all fields null),
# field_id_hash='709446a2', 12 instances across the corpus — a harvester bug
# (trailing empty checkbox_group record), not real page content. ---
_MALFORMED_NOTE = "Malformed extraction artifact: tag=None, every attribute null/empty, field_id_hash='709446a2' repeats identically across 12 pages/companies — a systemic harvester bug (trailing empty checkbox_group record appended per page), not real DOM content. Nothing to read/classify."
_malformed_count = 0
for ci, c in enumerate(data):
    for fi, f in enumerate(c["fields"]):
        if f.get("h") == "709446a2":
            ENTRIES.append({"ci": ci, "fi": fi, "action": "reject", "category": None, "note": _MALFORMED_NOTE})
            _malformed_count += 1

# --- acluinternships ---
confirm("acluinternships", 13, "writing_sample_request", "New category — requests a document/link submission, distinct from essay (free-text response) since it's asking for an attached work sample.")

# --- ada18 ---
confirm("ada18", 11, "work_authorized")

# --- alixpartners ---
reject("alixpartners", 5, "label='en-us12' — looks like a locale/config code artifact, not a real question. No section/nearby context to read any real meaning from.")

# --- alxafrica ---
confirm("alxafrica", 10, "essay")
confirm("alxafrica", 12, "salary_expectation")
confirm("alxafrica", 15, "other_followup", "Follow-up to a preceding 'Other, ALX staff or Media' choice — same other_followup family as 'please specify'.")
confirm("alxafrica", 16, "country_of_origin", "New category.")
confirm("alxafrica", 17, "country_of_residence", "New category.")
confirm("alxafrica", 18, "work_authorized", "'right to work in current country of residence without sponsorship' — work-authorization concept.")

# --- cypresscreekrenewables (remaining) ---
confirm("cypresscreekrenewables", 31, "other_followup", "Free-text follow-up to fi=29's nepotism_disclosure question (asks to name the relatives once fi=29 is answered yes).")
confirm("cypresscreekrenewables", 32, "willing_to_relocate", "'within commuting distance of Durham, NC' — same concept as astspacemobile's Midland/Odessa relocation question.")
confirm("cypresscreekrenewables", 35, "essay", "Section-fallback SCADA-monitoring technical scenario question — same family as Astranis's physics/propulsion technical essays.")

# --- d2l (non-filter fields) ---
reject("d2l", 0, "label='search filter label text' — literal placeholder-looking job-board search field.")
reject("d2l", 1, "'High Contrast' — accessibility display toggle, page chrome not a form field.")

# --- dataiku ---
confirm("dataiku", 12, "current_employee_of_company", "New category — 'Are you currently an employee at Dataiku?', present-tense status check, distinct from previously_employed_here.")
confirm("dataiku", 14, "needs_sponsorship")
confirm("dataiku", 17, "willing_to_relocate")
confirm("dataiku", 18, "how_heard_about_role")
confirm("dataiku", 22, "github_url")
confirm("dataiku", 23, "availability_commitment_confirmation", "'available for a 6-month full-time internship' — commitment confirmation, same family as celonis's 40h/week confirmation.")

# --- debutbiotech25 ---
confirm("debutbiotech25", 13, "needs_sponsorship", "'currently on a work visa (H1B, TN, OPT, etc.)' — current visa-status question, same underlying sponsorship concept.")
confirm("debutbiotech25", 15, "workplace_type", "'100% onsite in San Diego, CA' work-arrangement commitment.")

# --- defenseunicorns ---
confirm("defenseunicorns", 8, "military_branch", "New category — defense-sector specific, 'What branch of the US DoD are you currently with?'")
confirm("defenseunicorns", 10, "skillbridge_eligibility_date", "New category — DoD SkillBridge program eligibility date, very specific to defense-sector hiring but real and distinct.")
confirm("defenseunicorns", 11, "military_separation_date", "New category — 'estimated separation date' from military service.")
confirm("defenseunicorns", 15, "employee_referral")
confirm("defenseunicorns", 16, "event_attendance", "New category — 'Did you meet with or see Defense Unicorns at an event or conference (e.g. Kubecon)?'")
confirm("defenseunicorns", 18, "other_followup", "'If yes, what event?' — follow-up to fi=16.")
confirm("defenseunicorns", 19, "salary_expectation")
confirm("defenseunicorns", 20, "work_authorized")
confirm("defenseunicorns", 22, "security_clearance")
confirm("defenseunicorns", 24, "consent_ccpa_share_sale", "CCPA disclosure acknowledgment — same category as the already-confirmed 'share or sale of personal data' checkbox (Intrinsic Robotics/Motional/Scopely/SendBird), this is the disclosure-acknowledgment variant.")

# --- dvtrading ---
confirm("dvtrading", 23, "education_school", "'re-confirm the university you currently attend'")
confirm("dvtrading", 27, "relevant_industry_experience", "New category — 'relevant internship experience at a proprietary trading firm', industry-specific experience check.")
confirm("dvtrading", 29, "other_followup", "Conditional follow-up to fi=27.")
confirm("dvtrading", 30, "other_followup", "'If other, please specify'.")
confirm("dvtrading", 31, "country_of_residence")
confirm("dvtrading", 33, "state")
confirm("dvtrading", 34, "work_authorized")
confirm("dvtrading", 36, "needs_sponsorship")
confirm("dvtrading", 38, "other_followup", "'If yes, please provide your visa type and expiration date' — conditional follow-up.")
confirm("dvtrading", 39, "preferred_pronouns")
confirm("dvtrading", 43, "other_followup", "'If other, please explain'.")
confirm("dvtrading", 44, "consent_attestation_general", "'Terms & Conditions'.")

# --- ensono ---
reject("ensono", 3, "Hidden Salesforce-style CRM tracking field (name='Subscription_Insights__c_contact' — the '__c' suffix is Salesforce's custom-field naming convention), backend marketing/subscription tracking, not user-facing.")

# --- everstreamanalytics ---
confirm("everstreamanalytics", 10, "currently_based_in_country", "New category — 'currently based in the United States?' is a present-location yes/no check, distinct from work_authorized (legal ability to work) and willing_to_relocate (open to moving).")
confirm("everstreamanalytics", 12, "availability_commitment_confirmation", "Specific-hours/specific-duration commitment confirmation.")
confirm("everstreamanalytics", 14, "language_proficiency", "Mandarin Chinese proficiency.")

# --- feverup ---
confirm("feverup", 15, "field_of_study_relevance", "New category — 'Are you an Engineer or similar background (Maths, Physics, Statistics)?' asks about field-of-study RELEVANCE to the role, not the literal degree/discipline (education_discipline).")
confirm("feverup", 17, "academic_grade", "New category — 'average grade in university'.")
confirm("feverup", 18, "language_proficiency", "Spanish proficiency.")
confirm("feverup", 20, "language_proficiency", "English proficiency.")
confirm("feverup", 22, "internship_agreement_confirmation", "New category — 'able to sign an internship agreement with your University/Study Center' is specifically about a university-side paperwork requirement, distinct from consent_attestation_general.")
confirm("feverup", 24, "availability_start_date", "'What is your availability?'")
confirm("feverup", 26, "contract_length", "New category — 'potential length of your contract'.")
confirm("feverup", 28, "willing_to_relocate", "'currently living in Madrid or willing to move to Madrid'.")
confirm("feverup", 30, "work_authorized")
confirm("feverup", 32, "how_heard_about_role")
confirm("feverup", 34, "needs_sponsorship", "Long immigration-support/sponsorship question.")
confirm("feverup", 36, "preferred_pronouns")
confirm("feverup", 37, "consent_attestation_general", "Data-processing authorization paragraph.")
confirm("feverup", 39, "previously_employed_here", "New category — 'Have you previously been employed by this company?', distinct from current_employee_of_company (present tense).")
confirm("feverup", 42, "availability_start_date", "Section-fallback 'When would you be able to start your internship?'")

# --- gemini ---
confirm("gemini", 14, "currently_enrolled_status", "New category — 'currently enrolled in a bachelor's/associate's/master's degree program?' is an enrollment-STATUS check, distinct from education_school/education_degree (which/what) and graduation_date (when).")
confirm("gemini", 16, "essay", "'Please share 3-5 sentences explaining your interest in the Blockchain/Web3 industry.'")
confirm("gemini", 21, "previously_employed_here")
confirm("gemini", 23, "willing_to_relocate", "'open to relocating if not currently based near NYC'.")
confirm("gemini", 26, "consent_attestation_general", "Section-fallback 'Applicant Privacy Statement'.")

# --- gensyn ---
confirm("gensyn", 16, "publication_list", "New category — 'Publication List (linking to Google Scholar or similar is sufficient)', academic/research-specific.")
confirm("gensyn", 17, "github_url")
confirm("gensyn", 18, "currently_enrolled_status", "'currently enrolled in a PhD program?'")
confirm("gensyn", 20, "availability_hours_per_week", "'How many hours per week would you be able to work and for what duration of time?' — combined hours+duration question, close enough to the existing category to merge rather than split further.")
confirm("gensyn", 21, "availability_start_date", "'What is your potential start date?'")
confirm("gensyn", 22, "intended_work_country", "New category — 'What country do you intend to work from?', distinct from country_of_residence (asks intent/plan, not current location).")
confirm("gensyn", 23, "work_authorized")
confirm("gensyn", 25, "essay", "'What makes you a good fit for this role?'")

# --- globalrelay ---
confirm("globalrelay", 21, "work_authorized", "'legally authorized to work in Canada'.")
confirm("globalrelay", 23, "workplace_type", "'comfortable with a hybrid work environment'.")
confirm("globalrelay", 25, "consent_attestation_general", "'GDPR Notice'.")
confirm("globalrelay", 28, "department_interest", "Section-fallback field. VERIFIED via raw HTML (corpus/pages/5645073004.html.gz): real Greenhouse fieldset id='question_14158675004[]', genuine <legend> with the actual question text, required=true — NOT a job-board filter (checked explicitly after today's department_interest/location_preference correction, to avoid repeating that mistake).")

# --- golden-careers ---
_GC_NOTE = "Hidden CMS pagination/state field (block_uid, page_row_uid, location_uids, sort, etc.) — internal page-rendering state, not a form field."
for fi in [0, 1, 2, 3, 4, 5, 6, 7]:
    reject("golden-careers", fi, _GC_NOTE)
reject("golden-careers", 11, "Job-board search box ('Search by job title, location, department, category, etc.').")

# --- gostudent ---
reject("gostudent", 8, "Confirmed Cookiebot cookie-consent widget (id='CybotCookiebotDialogBodyContentCheckboxPersonalInformation'), same vendor prefix as previously-rejected cookie fields on this and other companies' pages.")

# --- groww ---
confirm("groww", 10, "nepotism_disclosure", "'relative/family member working currently in Groww'.")
confirm("groww", 12, "previously_employed_here")
confirm("groww", 14, "consent_background_check", "New category — 'consent for us to conduct your background verification (BGV) and reference checks', distinct from consent_ccpa_share_sale (data-privacy) and consent_attestation_general (information-accuracy).")
confirm("groww", 16, "personal_website", "'Please share your Portfolio here'.")

# --- guidepoint ---
confirm("guidepoint", 21, "salary_expectation", "'What is your desired compensation?'")
confirm("guidepoint", 22, "work_authorized", "'right to work in the EU'.")
confirm("guidepoint", 24, "preferred_contact_method", "New category — 'preferred way of communication to contact you? e.g., email, phone'.")
confirm("guidepoint", 25, "courses_remaining", "New category — 'how many courses do you have left until graduation'.")
confirm("guidepoint", 27, "language_proficiency", "'comfortable completing the interview process in English'.")
confirm("guidepoint", 29, "workplace_type", "'able to work from Athens in line with this arrangement'.")
confirm("guidepoint", 32, "needs_sponsorship", "Section-fallback visa/permit question.")
confirm("guidepoint", 33, "consent_attestation_general", "Section-fallback general information-accuracy attestation.")

# --- hala ---
confirm("hala", 10, "current_salary", "New category — 'What is your current salary?', distinct from salary_expectation (future/desired).")
confirm("hala", 11, "salary_expectation", "'What is your expected salary?'")
confirm("hala", 12, "nationality_check", "New category — 'Are you Saudi?' is a specific country-nationality eligibility check, distinct from general work_authorized.")
confirm("hala", 14, "nationality", "New category — 'What is your nationality?'")
confirm("hala", 16, "notice_period", "New category — 'What is your notice period?'")
confirm("hala", 18, "willing_to_relocate", "'Are you living in Riyadh?' — location/relocation check.")
confirm("hala", 20, "interview_availability", "New category — 'When is your available times for an interview?', distinct from availability_start_date (start-of-employment date).")
confirm("hala", 22, "essay", "'What do you know about Hala? And why you want to work for Hala?'")
confirm("hala", 23, "certifications", "New category — 'Kindly, write down professional certificates you have'.")

# --- horizonindustrieslimited ---
confirm("horizonindustrieslimited", 17, "criminal_background_disclosure", "New category — 'Have you ever been convicted of a crime?'")
confirm("horizonindustrieslimited", 19, "other_followup", "'If convicted, please explain' — follow-up to fi=17.")
confirm("horizonindustrieslimited", 20, "essay", "'Do you want to tell us anything else about yourself?'")
confirm("horizonindustrieslimited", 21, "needs_sponsorship", "Long immigration-support question.")
confirm("horizonindustrieslimited", 23, "consent_attestation_general", "'AI Policy for Hiring and Recruitment' agreement.")

with open("scratchpad/batch2_decisions.json", "w", encoding="utf-8") as f:
    json.dump(ENTRIES, f, indent=2)

rej = sum(1 for e in ENTRIES if e["action"] == "reject")
conf = sum(1 for e in ENTRIES if e["action"] == "confirm")
print(f"total entries: {len(ENTRIES)} (reject: {rej}, confirm: {conf}, of which malformed-hash rejects: {_malformed_count})")

new_cats = sorted(set(e["category"] for e in ENTRIES if e["action"] == "confirm"))
print(f"\ncategories touched ({len(new_cats)}):")
for c in new_cats:
    print(" ", c)
