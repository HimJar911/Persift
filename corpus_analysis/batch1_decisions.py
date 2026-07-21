"""Batch 1 (part 2) decisions — read every field individually against real
DOM/context evidence, not pattern-matched. Companies: asm, astranis,
astspacemobile, benesch, bitmovin, cannondesign, careers(hellofresh),
celonis, chainguard, checkbook, cityoffortworth, clarityinnovates, coupang,
cresta, cribl, cypresscreekrenewables.

Format matches manual_field_index_tags.py: {"ci", "fi", "action", "category", "note"}.
"""

import json

with open("scratchpad/oc_compact_full.json", encoding="utf-8") as f:
    data = json.load(f)


def ci_of(name):
    return next(i for i, c in enumerate(data) if c["company"] == name)


CI = {name: ci_of(name) for name in [
    "asm", "astranis", "astspacemobile", "benesch", "bitmovin", "cannondesign",
    "careers", "celonis", "chainguard", "checkbook", "cityoffortworth",
    "clarityinnovates", "coupang", "cresta", "cribl", "cypresscreekrenewables",
]}

ENTRIES = []


def reject(company, fi, note):
    ENTRIES.append({"ci": CI[company], "fi": fi, "action": "reject", "category": None, "note": note})


def confirm(company, fi, category, note=""):
    ENTRIES.append({"ci": CI[company], "fi": fi, "action": "confirm", "category": category, "note": note})


# --- asm: entire page is a job-board listing/filter page, no real form ---
_ASM_NOTE = "asm's whole crawled page is a job-listing/search page (9 total fields, all search boxes or empty unlabeled checkbox_group filters with zero section/options/nearby text) — not an application form. Consistent with the original apply_url-quality triage flag on this domain."
for fi in [0, 2, 3, 4, 5, 6, 7, 8]:
    reject("asm", fi, _ASM_NOTE)

# --- astranis: real application form, all confirmed ---
confirm("astranis", 18, "export_control", "New category. US Government space-tech export control question — 'therefore will you state which of the following applies to you' implies a multi-option export-control status answer.")
confirm("astranis", 20, "essay", "New category. Open-ended free-response question with no fixed answer shape.")
confirm("astranis", 21, "essay", "Role-specific technical screening essay question (physics/propulsion), company-unique content, same essay category — the interpreter can't meaningfully answer these beyond routing to LLM fallback/awaiting_review.")
confirm("astranis", 22, "essay", "Same technical-essay family as fi 21.")
confirm("astranis", 23, "essay", "Same technical-essay family as fi 21.")
confirm("astranis", 24, "essay", "Same technical-essay family as fi 21.")
confirm("astranis", 25, "availability_start_date", "'Please confirm which season you are applying for' — term/season selection, same concept as other availability_start_date instances.")
confirm("astranis", 27, "availability_start_date", "'When are you able to join Astranis as an intern?'")
confirm("astranis", 28, "availability_end_date", "New category — 'When do you plan on ending your internship?' is the end-date counterpart to availability_start_date, not seen before now.")
confirm("astranis", 29, "workplace_type", "On-site work-arrangement commitment question, same family as workplace_type.")

# --- astspacemobile ---
confirm("astspacemobile", 23, "age_18_or_older")
confirm("astspacemobile", 29, "language_proficiency", "New category — 'fluent in written and verbal English' language requirement, same family as the earlier Point72 (Japanese) / SES.ai (Mandarin) findings.")
confirm("astspacemobile", 31, "location_city", "'Current City, State'")
confirm("astspacemobile", 32, "willing_to_relocate", "New category — binary yes/no willingness to relocate to a SPECIFIC role location, distinct from location_preference (which is a multi-select of which offices/cities a candidate is open to in general).")
confirm("astspacemobile", 35, "availability_start_date", "'Earliest Start Date'")
confirm("astspacemobile", 38, "employee_referral", "New category — 'If you were referred by an AST employee, please enter their AST email.'")
confirm("astspacemobile", 39, "consent_attestation_general", "New category — general 'I certify the facts in this application are true' attestation, distinct from CCPA/privacy consent. Will likely accumulate more instances (Jump Trading's 'Notice at Collection', Woolpert's 'Privacy Acknowledgement', Celonis's confirmations below all belong here too).")

# --- benesch ---
confirm("benesch", 5, "phone", "Different id-scheme ('input_5') than the id-rule-confirmed phone cluster, but same concept, confirmed by label 'Phone*'.")
confirm("benesch", 7, "street_address", "New category — granular address component, distinct from location_city.")
confirm("benesch", 9, "state", "New category — granular address component.")
confirm("benesch", 10, "zip_code", "New category — granular address component.")
confirm("benesch", 13, "linkedin_url")
confirm("benesch", 14, "salary_expectation", "'What is your desired compensation range?'")
confirm("benesch", 15, "needs_sponsorship")
confirm("benesch", 16, "eeo_disability_status")
confirm("benesch", 18, "eeo_race_ethnicity", "'Race' — same category as eeo_race_ethnicity, shorter label.")
confirm("benesch", 26, "eeo_generic_decline_option", "New category — these 4 fields are individual OPTIONS within EEO question groups ('Not interested', 'Man', 'Black or of African descent', 'Asexual' — read via nearby text since label/section were empty), not standalone questions. Flagging as a distinct sub-concept since it's option-level, not question-level; may need remapping into the parent EEO categories once P1.4 handles group-vs-option structure properly rather than flat fields.")
confirm("benesch", 27, "eeo_generic_decline_option", "Option within an EEO gender question ('Man') — see fi 26 note.")
confirm("benesch", 28, "eeo_generic_decline_option", "Option within an EEO race question ('Black or of African descent') — see fi 26 note.")
confirm("benesch", 29, "eeo_generic_decline_option", "Option within an EEO sexual-orientation question ('Asexual') — see fi 26 note.")

# --- bitmovin ---
confirm("bitmovin", 10, "work_authorized")
confirm("bitmovin", 13, "program_affiliation", "New category — 'Are you part of a Bitmovin class at your school?' is a company-partnership-program affiliation question, same underlying concept as RocketLab's scholarship/fellowship question found earlier.")
confirm("bitmovin", 16, "workplace_type", "Commute-frequency commitment question, same family as workplace_type.")
confirm("bitmovin", 18, "consent_attestation_general", "'I agree with Privacy Notice for Recruitment' — general privacy attestation.")

# --- cannondesign: job-board filter page, all reject ---
_CD_NOTE_SEARCH = "Job-board search/sort/filter chrome on the listing page (confirmed pattern: bare search inputs, a 'Sort by' select, section='Keyword'), not the application form."
for fi in [0, 1, 2, 3, 4, 6]:
    reject("cannondesign", fi, _CD_NOTE_SEARCH)
_CD_NOTE_FILTER = "Confirmed via raw HTML (corpus/pages/8244421002.html.gz): lives inside a `data-filterdropdown-list` widget with a `sr-only` (screen-reader-only, visually hidden) heading — a job-board filter dropdown, same family as Anduril's rejected filter checkboxes, not a real application question."
for fi in [8, 10, 11, 14, 16, 17, 18, 19, 20, 21, 23, 24, 25, 27, 28, 29, 30, 31, 33, 34, 35, 36, 37, 38, 39, 40, 41, 43, 44, 45, 46, 47]:
    reject("cannondesign", fi, _CD_NOTE_FILTER)

# --- careers (hellofresh): job-board chrome ---
reject("careers", 0, "Job-board search box ('Enter Job Title or Location').")
reject("careers", 1, "Page-chrome language switcher (id='language-selector'), same pattern as previously-rejected language switchers.")
reject("careers", 2, "'To your colleagues or friends' — a 'share this job' widget fragment, not a form field.")

# --- celonis ---
confirm("celonis", 21, "work_authorized")
confirm("celonis", 25, "current_country_id_number", "New category — 'I confirm to have a valid NIE (spanish tax number)' is a country-specific tax/ID confirmation. Very narrow/company-specific; flagged as its own category rather than force-fit, may end up a rare long-tail category.")
confirm("celonis", 27, "education_degree", "Diploma confirmation, same underlying fact as education_degree (has a Bachelor/Master from a specific university type).")
confirm("celonis", 29, "availability_commitment_confirmation", "New category — 'available to work 40h per week for 12 months' is a commitment CONFIRMATION (yes/no), distinct from availability_hours_per_week (which asks the actual number).")
confirm("celonis", 31, "workplace_type", "On-site work-arrangement commitment.")
confirm("celonis", 33, "availability_start_date", "'Preferred Start Date'")
confirm("celonis", 37, "work_history_employer", "New category — 'Most Recent Employer'.")
confirm("celonis", 38, "work_history_title", "New category — 'Most Recent Job Title'.")
confirm("celonis", 39, "consent_attestation_general", "General information-accuracy attestation.")
confirm("celonis", 41, "consent_attestation_general", "Privacy Notice acknowledgment.")
confirm("celonis", 43, "program_affiliation", "'Which Celonis campus event or university career fair did you attend?' — company-program/event affiliation, same family as bitmovin's program_affiliation.")
confirm("celonis", 45, "eeo_gender_identity")
confirm("celonis", 46, "essay", "'What does The Best Team Wins mean to you?' — open-ended company-culture essay question.")

# --- chainguard ---
confirm("chainguard", 14, "education_school", "'What university are you currently attending?'")
confirm("chainguard", 15, "graduation_date", "'What year do you plan to graduate?'")
confirm("chainguard", 16, "essay", "'Describe the type of role you would like to have within that department' — open-ended.")
confirm("chainguard", 17, "availability_start_date", "'What semester and year are you looking for an internship?'")
confirm("chainguard", 18, "availability_hours_per_week")
confirm("chainguard", 23, "needs_sponsorship", "Section-fallback field (empty label, section IS the sponsorship question) — matches the already-confirmed needs_sponsorship category exactly.")
confirm("chainguard", 24, "department_interest", "Section-fallback field (empty label, section='What department(s) are you most interested in for your internship?') — matches department_interest exactly.")

# --- checkbook ---
confirm("checkbook", 11, "essay", "Open-ended 'what would you be doing at Checkbook' creative-response question.")
confirm("checkbook", 12, "location_city", "'What city and state are you located in?'")

# --- cityoffortworth: entire page is government job-board chrome, all reject ---
_CFW_NOTE = "cityoffortworth's crawled page is a government job-board/listing page: ASP.NET hidden viewstate fields (__VIEWSTATE, __EVENTTARGET, etc.), 'By Phrase/Job Type/Department' filter widgets (section='Job Board'), and literal Google Translate widget internals (goog-gt-votingInput*). No real application-form field observed on this page."
for fi in [0, 1, 2, 3, 4, 7, 8, 9, 10, 14, 15, 16, 17, 18]:
    reject("cityoffortworth", fi, _CFW_NOTE)

# --- clarityinnovates ---
confirm("clarityinnovates", 18, "mailing_address", "New category — 'Current Mailing Address', distinct from location_city/street_address (single combined field here).")
confirm("clarityinnovates", 19, "security_clearance", "'Current clearance level' — same category as RocketLab's earlier-found security_clearance.")
confirm("clarityinnovates", 21, "consent_attestation_general", "Location/date acknowledgment attestation.")
confirm("clarityinnovates", 23, "current_school_year", "New category — 'School Year completed by the beginning of Summer 2027' asks what year of school (freshman/sophomore/etc.) the candidate will have completed, distinct from graduation_date (a specific future date).")

# --- coupang: job-board filter chrome ---
_COUPANG_NOTE = "section='Filter jobs' — job-board listing filter widget, not the application form. Consistent with the earlier-confirmed reject on this exact company's 'Keywords'/'l-team' search fields."
reject("coupang", 3, _COUPANG_NOTE)
reject("coupang", 4, _COUPANG_NOTE)
reject("coupang", 5, _COUPANG_NOTE)

# --- cresta ---
confirm("cresta", 8, "essay", "Open-ended 'type of problems you most enjoy working on' question.")

# --- cribl ---
reject("cribl", 0, "Bare site search input (id='searchInput'), same pattern as other rejected search boxes.")

# --- cypresscreekrenewables ---
confirm("cypresscreekrenewables", 25, "work_authorized", "'legally eligible to work in the U.S.'")
confirm("cypresscreekrenewables", 29, "nepotism_disclosure", "New category — 'close relatives who work at Cypress Creek' conflict-of-interest/nepotism disclosure question.")

with open("scratchpad/batch1_decisions.json", "w", encoding="utf-8") as f:
    json.dump(ENTRIES, f, indent=2)

rej = sum(1 for e in ENTRIES if e["action"] == "reject")
conf = sum(1 for e in ENTRIES if e["action"] == "confirm")
print(f"total entries: {len(ENTRIES)} (reject: {rej}, confirm: {conf})")

new_cats = sorted(set(e["category"] for e in ENTRIES if e["action"] == "confirm"))
print(f"\ncategories touched ({len(new_cats)}):")
for c in new_cats:
    print(" ", c)
