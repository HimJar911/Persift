"""Batch 3 decisions. Opens with a correction: Anduril fi 0-13 and d2l's
full filter-widget field range were discussed in a prior conversation turn
but never actually written to the tagging pipeline — the same class of
mistake the founder caught earlier with 617mediagroup. Fixed properly this
time with direct raw-HTML verification (not positional assumption) before
writing anything.
"""

import json

with open("scratchpad/oc_compact_full.json", encoding="utf-8") as f:
    data = json.load(f)


def ci_of(name):
    return next(i for i, c in enumerate(data) if c["company"] == name)


CI = {name: ci_of(name) for name in [
    "andurilindustries", "d2l", "horizonindustrieslimited", "impact", "inmobi",
    "instawork", "inter", "interstates", "intrinsicrobotics", "jumptrading",
    "karya", "krafton", "lockwood", "lucidsoftware", "marvelfusion",
    "mks2technologies", "moloco", "neuralink", "nice", "nuro", "offerup",
    "ogilvy",
]}

ENTRIES = []


def reject(company, fi, note):
    ENTRIES.append({"ci": CI[company], "fi": fi, "action": "reject", "category": None, "note": note})


def confirm(company, fi, category, note=""):
    ENTRIES.append({"ci": CI[company], "fi": fi, "action": "confirm", "category": category, "note": note})


# --- CORRECTION: andurilindustries fi 0-13 — previously discussed but never
# written. Re-verified via raw HTML (corpus/pages/5121683007.html.gz), NOT
# assumed from an earlier (wrong) positional guess. Real result: fi 0-4 are
# part of the same job-board 'Open Roles Filters' widget already confirmed
# fake (DEPARTMENT/LOCATION/EMPLOYMENT TYPE dropdown buttons + their
# internal search inputs) — NOT First/Last/Email/LinkedIn as first assumed.
# The real First Name/Last Name/Email/LinkedIn/Resume fields are actually
# at fi 6-9 (fi 10 already confirmed as resume_upload separately). ---
_AR_FILTER_NOTE = "Confirmed via raw HTML: part of the 'open-roles__filters' / aria-label='Open Roles Filters' job-board widget (DEPARTMENT/LOCATION/EMPLOYMENT TYPE dropdown toggle buttons and their internal controls) — same rejected widget as fi 14-121. NOT the real application form's name/email/LinkedIn fields (those are at fi 6-9, confirmed separately)."
for fi in [0, 1, 2, 3, 4]:
    reject("andurilindustries", fi, _AR_FILTER_NOTE)
reject("andurilindustries", 5, "Confirmed via raw HTML: class='search', inside open-roles__search-container — job-board search box.")
confirm("andurilindustries", 6, "first_name", "Confirmed via raw HTML: <label class='required'>First Name</label>, type=text, name='First Name'.")
confirm("andurilindustries", 7, "last_name", "Confirmed via raw HTML: <label class='required'>Last Name</label>.")
confirm("andurilindustries", 8, "email", "Confirmed via raw HTML: <label class='required'>Email Address</label>, type=email.")
confirm("andurilindustries", 9, "linkedin_url", "Confirmed via raw HTML: <label>LinkedIn URL</label>, type=url.")
# fi 10 (Resume) already confirmed resume_upload in an earlier round — not re-added here.
# fi 11 (Which type of role are you interested in?) already confirmed department_interest earlier — not re-added.
confirm("andurilindustries", 12, "consent_attestation_general", "Confirmed via raw HTML: label text is placeholder ('Type here') but the REAL <label> reads \"By submitting you agree to Gem's terms and privacy policy.\" (this site runs on the Gem ATS platform, gem.com) — a required consent checkbox, not the 'Any additional information' field the label position first suggested.")
reject("andurilindustries", 13, "Confirmed via raw HTML: group-level wrapper for the DEPARTMENT filter widget (same as fi 0-4, fi 14-121) — heading literally 'DEPARTMENT'.")

# --- CORRECTION: d2l — full filter-widget field range (fi 0-24), not just
# the subset caught in the first correction pass. Re-verified: fi 0 is the
# search box, fi 1 is an accessibility-widget toggle (id='accessibility-
# dropdown'), fi 2-24 are all department/employment-type/location filter
# options from the SAME name='filter-group-1_N' widget already confirmed
# fake in the department_interest/location_preference correction. ---
reject("d2l", 0, "Job-board search box.")
reject("d2l", 1, "Confirmed via raw HTML: id='accessibility-dropdown' — page accessibility widget toggle ('High Contrast'), not a form field.")
_D2L_FILTER_NOTE = "Confirmed via raw HTML (corpus/pages/7875384.html.gz): name='filter-group-1_N' job-board filter widget (department/employment-type/location options) — same widget already confirmed fake for 'Marketing'/'Finance'/'Sales'/'No Department' etc. in the department_interest/location_preference correction."
for fi in [2, 6, 8, 10, 12]:
    reject("d2l", fi, _D2L_FILTER_NOTE)
# fi 3(Corporate),4(Finance),5(Marketing),7(Product Development),9(Sales),
# 11(Full-time), 13-24(location names) — already rejected in the earlier
# department_interest/location_preference correction pass; not duplicated here.

# --- horizonindustrieslimited ---
confirm("horizonindustrieslimited", 28, "education_degree", "\"Have you completed your Bachelor's degree?\" — degree-completion status.")
confirm("horizonindustrieslimited", 30, "needs_sponsorship", "'Do you hold an OPT VISA?' — visa-status question, same sponsorship-adjacent category.")

# --- impact ---
confirm("impact", 9, "notice_period", "'current notice period/when are you available to start a new position' — combined notice-period + availability question, closer to notice_period given the framing leads with notice period.")

# --- inmobi ---
confirm("inmobi", 11, "current_salary", "'current Stiphend' (stipend) — same category as current_salary.")
confirm("inmobi", 12, "salary_expectation", "'expected Stiphend'.")
confirm("inmobi", 13, "workplace_type", "'comfortable working from Bangalore office for 5 days'.")
confirm("inmobi", 15, "availability_start_date", "'How soon can you join us?'")

# --- instawork ---
confirm("instawork", 12, "work_authorized")

# --- inter (Brazilian company, Portuguese-language form) ---
confirm("inter", 4, "phone", "section='Telefone' (Portuguese for 'Phone') — same phone concept, different language.")
confirm("inter", 17, "national_id_number", "New category — 'CPF' is Brazil's national taxpayer ID number, same family as celonis's Spanish NIE (current_country_id_number) but this is common/structural enough (every Brazilian form will ask for CPF) to warrant its own clearer name.")
confirm("inter", 18, "current_employee_of_company", "'Você trabalha atualmente no Inter?' = 'Do you currently work at Inter?'")
confirm("inter", 20, "location_preference", "'em qual ou quais escritórios você tem interesse em atuar?' = 'which office(s) are you interested in working at?' — genuine application-form multi-select (id='question_8440646005[]', standard Greenhouse question format, NOT a job-board filter — verified by id pattern matching the confirmed-real question_NNNNN family, distinct from today's filter-widget corrections which all had non-question_ ids).")
confirm("inter", 22, "employee_referral", "'Você conhece alguém que trabalha no Inter?' = 'Do you know someone who works at Inter?'")
confirm("inter", 24, "other_followup", "Follow-up: 'If yes to the previous question, what is the full name of the employee?'")
confirm("inter", 25, "certifications", "'Você possui alguma certificação?' = 'Do you have any certification?'")
confirm("inter", 27, "resume_upload", "'Anexar' = 'Attach', itype=file — same attach-resume pattern confirmed earlier for English-language forms.")
confirm("inter", 28, "consent_attestation_general", "Long LGPD (Brazilian data protection law) privacy-policy consent paragraph.")
confirm("inter", 30, "language_proficiency", "'nível de fluência na língua inglesa' = English fluency level.")
confirm("inter", 32, "language_proficiency", "Spanish fluency level.")
confirm("inter", 34, "education_degree", "'Você possui curso superior completo?' = 'Do you have a completed higher-education degree?'")
confirm("inter", 36, "other_followup", "Conditional follow-up: 'If yes to the previous question, what course did you graduate in? If no, fill NA.'")
confirm("inter", 38, "current_salary", "'Informe seu salário atual/último' = 'State your current/last salary'.")
confirm("inter", 39, "current_benefits", "New category — 'Informe seus Benefícios atuais/últimos' = 'State your current/last benefits' — distinct from salary.")
confirm("inter", 40, "consent_attestation_general", "Long AI-interview-transcription consent paragraph (LGPD-compliant).")

# --- interstates ---
confirm("interstates", 18, "other_followup", "'If you selected Event, Employee, or Other, please specify below'.")
confirm("interstates", 19, "previously_employed_here")
confirm("interstates", 21, "age_18_or_older")
confirm("interstates", 25, "needs_sponsorship")
confirm("interstates", 27, "consent_attestation_general", "'understand the job requirements... able to perform essential job functions' — ADA-related work-capability attestation, same general-consent family.")
confirm("interstates", 29, "consent_sms_communication", "New category — explicit SMS/texting consent for application-process communications (distinct from general privacy/data consent), names a specific third-party vendor (Grayscale Labs).")

# --- intrinsicrobotics ---
reject("intrinsicrobotics", 0, "Empty label/section/id/context — cannot classify with any confidence. Sits among page-chrome fields (fi 4-5 confirmed newsletter signup) on this company's general contact page, not a job application.")
reject("intrinsicrobotics", 1, "Empty select with no context, same page-chrome region as fi 0.")
reject("intrinsicrobotics", 2, "'ALL LOCATIONSMountain View, CaliforniaMunich, GermanySingapore' — concatenated option text of an office-location FILTER dropdown (option text run together with no separators is a giveaway of a generic multi-option select, consistent with other job-board filters found this session), not an application field.")
reject("intrinsicrobotics", 4, "section='Subscribe for occasional news and updates' — newsletter signup, not the application form.")
reject("intrinsicrobotics", 5, "Same newsletter-signup section as fi=4; hidden field carrying the privacy-policy disclaimer text for that signup form.")

# --- jumptrading ---
confirm("jumptrading", 17, "notice_period", "'Non-compete/Notice period comments'.")
confirm("jumptrading", 18, "needs_sponsorship")
confirm("jumptrading", 20, "education_school")
confirm("jumptrading", 22, "education_discipline", "'What degree are you currently pursuing?' — maps to discipline/degree-in-progress, same family as education_discipline.")
confirm("jumptrading", 26, "competing_offers_disclosure", "New category — 'Do you currently have any offers from other firms or deadlines we should be aware of?'")
confirm("jumptrading", 28, "other_followup", "Follow-up: 'please tell us about your offers and deadlines'.")
confirm("jumptrading", 30, "other_followup", "'If you selected Other above, please specify'.")
confirm("jumptrading", 32, "consent_attestation_general", "Section-fallback 'Notice at Collection' GDPR/CCPA-style data-processing notice.")
confirm("jumptrading", 33, "location_preference", "Section-fallback 'which other locations are you interested in relocating to' — genuine relocation-preference question (id-less section-fallback field, but content matches the confirmed category, not a filter widget — this form has no job-board filter chrome elsewhere on the page).")

# --- karya ---
confirm("karya", 19, "essay", "'Do you have open source contribution? Please paste a link and explain briefly what you did' — open-ended with a link+explanation ask, essay-shaped.")

# --- krafton (Korean-language form) ---
confirm("krafton", 4, "phone", "section='전화' (Korean for 'Phone').")
confirm("krafton", 11, "consent_attestation_general", "'Precautions for submitting a resume' acknowledgment (bilingual Korean/English).")
reject("krafton", 12, "label='선택...' (Korean for 'Select...') — same generic combobox-placeholder pattern already confirmed as noise (matches the earlier 'Select...' reject), this is just the Korean-language version of the same fallback string.")
confirm("krafton", 13, "resume_upload", "'파일 첨부' = 'File attachment', itype=file, tied to the resume-submission question.")
confirm("krafton", 14, "personal_website", "'Portfolio (Paste link)' — bilingual, matches personal_website/portfolio category.")
confirm("krafton", 15, "resume_upload", "Second 'File attachment' field — a portfolio file upload, same resume_upload category (file attachment mechanism, distinct question but same field TYPE).")
confirm("krafton", 16, "military_branch", "'Please indicate whether you are currently subject to one of the following types of military service' — South Korea has mandatory military service disclosure on job applications, same military_branch/service-status family.")
reject("krafton", 17, "Korean 'Select...' placeholder, same as fi=12.")
confirm("krafton", 18, "consent_attestation_general", "'Notice on the Collection and Use of Personal Information' — Korean PIPA (privacy law) consent.")
reject("krafton", 19, "Korean 'Select...' placeholder.")
confirm("krafton", 20, "consent_attestation_general", "'Notice on the Collection and Use of Sensitive Information' — related PIPA consent, sensitive-data variant.")
reject("krafton", 21, "Korean 'Select...' placeholder.")
confirm("krafton", 22, "eeo_veteran_status", "'Please indicate whether you are eligible for a veteran service' — Korean veteran-preference disclosure, same eeo_veteran_status family (Korea has legally mandated veteran hiring preference disclosure, similar EEO purpose to the US veteran-status question).")
reject("krafton", 23, "Korean 'Select...' placeholder.")
confirm("krafton", 24, "eeo_disability_status", "'Please indicate whether you are a registered person with disabilities' — same eeo_disability_status family.")
reject("krafton", 25, "Korean 'Select...' placeholder.")

# --- lockwood ---
confirm("lockwood", 13, "education_degree", "'highest level of education'.")
confirm("lockwood", 15, "relevant_industry_experience", "'years of office experience' — role-relevant-experience question, same family as dvtrading's relevant_industry_experience.")
confirm("lockwood", 16, "workplace_type", "'fully in-office... willing to commute'.")

# --- lucidsoftware ---
confirm("lucidsoftware", 19, "state")
confirm("lucidsoftware", 21, "current_school_year")
confirm("lucidsoftware", 22, "academic_grade", "'most recent cumulative GPA' — same academic_grade category (grade/GPA), broader than just 'average grade'.")
confirm("lucidsoftware", 23, "willing_to_relocate")
confirm("lucidsoftware", 27, "salary_expectation", "'desired compensation (hourly rate)'.")

# --- marvelfusion ---
confirm("marvelfusion", 10, "availability_commitment_confirmation", "'available to work full-time for the entire duration of the internship'.")
confirm("marvelfusion", 12, "availability_start_date", "'earliest possible start date'.")
confirm("marvelfusion", 14, "availability_hours_per_week", "'How long would you be available for the internship?' — duration question, same family (availability_hours_per_week already covers combined hours+duration per gensyn's earlier confirm).")
confirm("marvelfusion", 16, "currently_enrolled_status", "'currently enrolled as a student... mandatory part of your study program'.")
confirm("marvelfusion", 18, "essay", "Detailed hands-on-experience question requesting explanation.")
confirm("marvelfusion", 19, "mailing_address", "'current address'.")
confirm("marvelfusion", 20, "needs_sponsorship")
confirm("marvelfusion", 22, "language_proficiency", "German proficiency.")

# --- mks2technologies (all military-transition-specific fields) ---
confirm("mks2technologies", 16, "military_branch")
confirm("mks2technologies", 17, "military_specialty_code", "New category — 'AFSC / MOS' (Air Force Specialty Code / Military Occupational Specialty) is a specific military job-classification code, distinct from military_branch.")
confirm("mks2technologies", 18, "current_job_title")
confirm("mks2technologies", 19, "military_rank", "New category — 'Rank'.")
confirm("mks2technologies", 20, "military_time_in_service", "New category — 'Time in Service'.")
confirm("mks2technologies", 21, "military_separation_date", "'Date of Separation/Retirement' — same category as defenseunicorns' military_separation_date.")
confirm("mks2technologies", 22, "skillbridge_eligibility_date", "'Skill bridge Start Date' — same category as defenseunicorns' skillbridge_eligibility_date.")
confirm("mks2technologies", 23, "contract_length", "'Desired Duration'.")
confirm("mks2technologies", 24, "department_interest", "'Desired Position' — role/department preference, same family as department_interest.")

# --- moloco ---
confirm("moloco", 13, "first_name", "'Legal First Name (English)' — same first_name category, with a legal-name qualifier (common on forms targeting international/bilingual-name candidates).")
confirm("moloco", 14, "last_name", "'Legal Last Name (English)'.")
confirm("moloco", 16, "work_authorized")
confirm("moloco", 18, "needs_sponsorship")
confirm("moloco", 20, "military_branch", "'(Korean male only) Please share your military status' — same Korea-specific mandatory-service disclosure family as krafton's military_branch.")
confirm("moloco", 21, "language_proficiency", "'speak both English and Korean'.")
confirm("moloco", 23, "graduation_date")
confirm("moloco", 24, "availability_start_date", "'available date of joining for the internship'.")
confirm("moloco", 25, "availability_commitment_confirmation", "'available to work for 3 months as a full-time'.")
confirm("moloco", 27, "essay", "'What interests you about MOLOCO? Please provide 2-3 sentences.'")

# --- neuralink ---
confirm("neuralink", 17, "essay", "'exceptional ability' STAR-format essay question, 'First example:' — part of a 3-part essay series.")
confirm("neuralink", 18, "essay", "'Second example:' — same essay series as fi=17.")
confirm("neuralink", 19, "essay", "'Third example:' — same essay series.")
confirm("neuralink", 20, "relevant_industry_experience", "'prior internship or co-op experience'.")
confirm("neuralink", 22, "graduation_date")
confirm("neuralink", 25, "personal_website", "'Additional Link' — portfolio/personal-link category, generic enough to fold into personal_website rather than invent a narrower category.")
confirm("neuralink", 29, "needs_sponsorship")
confirm("neuralink", 31, "workplace_type", "'willing and able to work entirely on-site'.")
confirm("neuralink", 33, "willing_to_relocate", "'no relocation assistance... able to relocate on your own'.")
confirm("neuralink", 35, "availability_start_date", "'What internship season are you interested in?'")
confirm("neuralink", 37, "availability_start_date", "'Ideal start date in office'.")
confirm("neuralink", 39, "location_preference", "'Which onsite location would you like to apply to?'")

# --- nice ---
confirm("nice", 9, "nepotism_disclosure", "'first-degree relatives... currently employed by NICE'.")
confirm("nice", 11, "previously_employed_here")
confirm("nice", 13, "needs_sponsorship", "'need a visa / work permit'.")

# --- nuro ---
confirm("nuro", 13, "work_authorized")
confirm("nuro", 15, "needs_sponsorship")
confirm("nuro", 17, "workplace_type", "Specific hybrid-schedule commitment question.")

# --- offerup ---
confirm("offerup", 10, "how_heard_about_role")
confirm("offerup", 11, "willing_to_relocate", "'located in the Seattle/Bellevue area for the duration of the internship'.")
confirm("offerup", 13, "work_authorized")
confirm("offerup", 15, "needs_sponsorship", "'need any immigration support' with a details request — sponsorship-adjacent, folded into needs_sponsorship rather than treated as a separate essay since the core ask is a sponsorship yes/no+details.")
confirm("offerup", 16, "salary_expectation", "'Expected Compensation?'")

# --- ogilvy ---
reject("ogilvy", 2, "Hidden field, empty everything, no readable content — cannot classify.")
confirm("ogilvy", 3, "current_job_title", "'Job Title', required — same current_job_title category (this is on Ogilvy's general talent-network 'Contact Us' form, but the field itself asks the same underlying fact as work_history_title/current_job_title).")
reject("ogilvy", 10, "Hidden field, empty everything, no readable content.")
reject("ogilvy", 11, "Hidden field, empty everything, no readable content.")

with open("scratchpad/batch3_decisions.json", "w", encoding="utf-8") as f:
    json.dump(ENTRIES, f, indent=2)

rej = sum(1 for e in ENTRIES if e["action"] == "reject")
conf = sum(1 for e in ENTRIES if e["action"] == "confirm")
print(f"total entries: {len(ENTRIES)} (reject: {rej}, confirm: {conf})")

new_cats = sorted(set(e["category"] for e in ENTRIES if e["action"] == "confirm"))
print(f"\ncategories touched ({len(new_cats)}):")
for c in new_cats:
    print(" ", c)
