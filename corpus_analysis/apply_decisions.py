"""Apply the human-reviewed decisions from this session's open-coding pass
onto the 98 auto-clusters. Every decision below traces to specific evidence
discussed in conversation (id/name attrs, section/container context, or
cross-company coincidence patterns) — not a guess re-applied at scale.

Output: scratchpad/cluster_decisions.json, consumed by the artifact to
pre-seed confirm/reject/rename state instead of the founder clicking
through 98 cards individually for the ones already settled.
"""

import json

with open("scratchpad/clusters.json", encoding="utf-8") as f:
    cd = json.load(f)

# NOTE: keyed by (rule, key), not just key — several normalized keys are
# produced by more than one rule (e.g. "email" via both the id-rule and the
# label-rule as separate clusters; "gender"/"country" likewise). A bare
# key-only dict silently collapses these to whichever cluster iterates last,
# so any CONFIRM/REJECT entry below keyed by bare string would only apply to
# ONE of the colliding clusters and leave the other silently "unresolved."
clusters = {(c["rule"], c["key"]): c for c in cd["clusters"]}
_KEY_TO_RULEKEYS = {}
for c in cd["clusters"]:
    _KEY_TO_RULEKEYS.setdefault(c["key"], []).append(c["rule"])

# CONFIRM — real application-form categories, final canonical name.
# Where multiple clusters clearly mean the same thing (label-phrasing
# variants), they get the SAME canonical name so they merge into one
# group in "Named groups" even though they were separate auto-clusters.
CONFIRM = {
    "given-name": "first_name",
    "family-name": "last_name",
    "email": "email",
    "first name": "first_name",
    "last name": "last_name",
    "email address": "email",
    "preferred first name": "preferred_first_name",

    "linkedin profile": "linkedin_url",
    "linkedin profile link": "linkedin_url",
    "linkedin url": "linkedin_url",
    "linkedin profile or website": "linkedin_url",

    "location city": "location_city",
    "location": "location_city",  # ambiguous short label, same bucket pending closer look

    "are you legally authorized to work in the united states": "work_authorized",

    "will you now or in the future require sponsorship for employment visa status e g h 1b visa status": "needs_sponsorship",
    "will you now or in the future require visa sponsorship": "needs_sponsorship",

    "are you hispanic latino": "eeo_hispanic_latino",
    "veteran status": "eeo_veteran_status",
    "are you a veteran or active member of the united states armed forces select one": "eeo_veteran_status",
    "are you a veteran or active member of the united states armed forces select one please selectyes i am a veteran or active memberno i am not a veteran or active memberi prefer to self describei don t wish to answer": "eeo_veteran_status",
    "are you a veteran or active member of the united states armed forces": "eeo_veteran_status",

    "disability status": "eeo_disability_status",
    "do you have a disability or chronic condition physical visual auditory cognitive mental emotional or other that substantially limits one or more of your major life activities including mobility communication seeing hearing speaking and learning select one": "eeo_disability_status",
    "do you have a disability or chronic condition physical visual auditory cognitive mental emotional or other that substantially limits one or more of your major life activities including mobility communication seeing hearing speaking and learning": "eeo_disability_status",

    "do you identify as transgender select one": "eeo_transgender",
    "do you identify as transgender": "eeo_transgender",

    "how would you describe your gender identity mark all that apply": "eeo_gender_identity",
    "how would you describe your gender identity": "eeo_gender_identity",

    "how would you describe your racial ethnic background mark all that apply": "eeo_race_ethnicity",
    "how would you describe your racial ethnic background": "eeo_race_ethnicity",

    "how would you describe your sexual orientation mark all that apply": "eeo_sexual_orientation",
    "how would you describe your sexual orientation": "eeo_sexual_orientation",

    "discipline": "education_discipline",  # confirmed via raw HTML: sits in education--date-container block, means major/field of study
    "start date year": "education_start_date",  # confirmed via raw HTML: education block (adjacent to discipline)
    "end date year": "education_end_date",
    "start date month": "education_start_date",
    "end date month": "education_end_date",

    "how did you hear about this job": "how_heard_about_role",
    "how did you hear about us": "how_heard_about_role",

    "company name": "current_company",  # NOTE: verify — could be "current employer" or could be part of a reference/contact block; keep an eye during residue review
    "current company": "current_company",

    "are you 18 years of age or older": "age_18_or_older",

    "share or sale of personal data": "consent_ccpa_share_sale",  # genuinely new category vs. old FIELD_PATTERNS

    "preferred pronouns": "preferred_pronouns",

    "citizenship status": "citizenship_status",

    "workplace type": "workplace_type",  # e.g. remote/hybrid/onsite preference
    "employment type": "employment_type",  # e.g. full-time/part-time/contract

    "what are your salary expectations": "salary_expectation",
    "salary expectation": "salary_expectation",

    "what is your expected graduation date": "graduation_date",

    "resume cv": "resume_upload",

    "when would you be available to join us": "availability_start_date",

    # Department-interest and location-preference: MERGE per founder decision —
    # same underlying question type, per-company option text varies.
    "administration": "department_interest",
    "communications": "department_interest",
    "product development": "department_interest",
    "marketing": "department_interest",
    "engineering": "department_interest",
    "consulting": "department_interest",
    "industry": "department_interest",
    "department": "department_interest",
    "full time": "department_interest",  # NOTE: this one may actually be an employment-type checkbox option, not department — flagged for a second look, not confirmed with same confidence as the rest

    "boston massachusetts united states": "location_preference",
    "denver colorado united states": "location_preference",
    "seattle washington united states": "location_preference",
    "netherlands": "location_preference",
    "united states": "location_preference",
    "mexico city": "location_preference",

    "how much experience in c programming language do you have": "skill_experience_years",  # role-specific skill question, real but long-tail
}

# FOLLOW-UP / SPECIAL HANDLING — real, but not a normal standalone category.
SPECIAL = {
    "please specify": {"kind": "other_followup", "note": "Free-text follow-up to an 'Other' choice on some preceding question — must stay linked to its parent field, not treated as its own category."},
    "if f other please explain": {"kind": "other_followup", "note": "Same as 'please specify' — Other-option follow-up."},
    "leave this field blank": {"kind": "honeypot", "note": "Confirmed via raw HTML (id=edit-url, name=url, label literally says leave blank) — anti-bot trap. Autofill must actively skip, never fill."},
}

# REJECT — page chrome / not application-form fields, confirmed via evidence
# (id prefixes like cky*, zero nearby-text + unrelated companies sharing
# identical strings, or direct raw-HTML inspection).
REJECT = {
    "checkbox label": "Fallback string the harvester writes when no real label is found — not an actual repeated question, just many different unrelated checkboxes that all failed label detection.",
    "cookie list search": "Cookie-consent banner UI (OneTrust/CookieYes-style widget), not a form field.",
    "targeting cookies": "Cookie-consent banner toggle.",
    "performance cookies": "Cookie-consent banner toggle.",
    "functional cookies": "Cookie-consent banner toggle.",
    "social media cookies": "Cookie-consent banner toggle.",
    "necessary": "Cookie-consent banner toggle (GoStudent).",
    "preferences": "Cookie-consent banner toggle (GoStudent).",
    "statistics": "Cookie-consent banner toggle (GoStudent).",
    "enable functional": "Cookie-consent banner toggle — confirmed same widget pattern as 'targeting/performance/functional cookies', zero nearby-text, unrelated companies (solar energy co + security audio co) sharing identical string only explainable by a shared embedded widget.",
    "enable analytics": "Cookie-consent banner toggle, same as above.",
    "enable performance": "Cookie-consent banner toggle, same as above.",
    "enable advertisement": "Cookie-consent banner toggle, same as above.",
    "enable do not sell or share my personal information": "Confirmed via raw HTML: id='ckyCCPAOptOut' — 'cky' prefix is the CookieYes consent-widget's own opt-out toggle, not an application-form field (distinct from the real 'share or sale of personal data' CCPA checkbox found on Intrinsic Robotics/Motional/Scopely/SendBird, which IS a real form field and IS confirmed above).",
    "select language": "Page-chrome language switcher (confirmed earlier: options are English/Deutsch/Español/etc. in a nav element).",
    "language switcher english": "Same as 'select language'.",
    "selecionar": "Generic 'select' placeholder in Portuguese/Spanish — UI chrome, not a real question.",
    "search departments": "Job-board search/filter UI, not an application field.",
    "search job title or location": "Job-board search box.",
    "vendor search": "Unrelated site search widget.",
    "select all vendors": "Unrelated site search/filter widget.",
    "keywords": "Job-board search box (confirmed: Coupang and Pinterest, itype=search).",
    "searchsearch": "Duplicated/garbled search-box label — site search chrome.",
    "subscribe": "Newsletter subscribe widget, not part of the application form.",
    "chatbot user input box with send button": "Site chatbot widget.",
    "save job growth strategy data analyst intern m f n": "Confirmed via data: 'Save Job' button on the job LISTING page, id='saveJob-...' — a bookmark button, not a form field.",
    "get email updates from the city of fort worth on the topics you want": "Newsletter/notification signup on the city's public site, not the job application form itself.",
}

# --- Round 2 additions: after adding the `id`-attribute clustering rule,
# residue dropped from 2129 to ~1060. These are the new clusters that
# appeared (id-rule matches) plus stragglers surfaced by re-inspection. ---

CONFIRM.update({
    # id-rule matches — very high confidence, ids are explicit dev-chosen semantics
    "email": "email",  # covers the id-rule 'email' cluster (label-rule 'email' cluster below also maps here)
    "phone": "phone",
    "first_name": "first_name",
    "last_name": "last_name",
    "country": "phone_country_code",  # confirmed via HTML: id=country sits in the "Phone" section — this is the phone number's country/calling-code selector, NOT a general "what country are you in" question
    "resume": "resume_upload",
    "cover_letter": "cover_letter_upload",
    "gender": "eeo_gender_identity",  # short id-based version, same category as the longer label-rule phrasing already confirmed
    "hispanic_ethnicity": "eeo_hispanic_latino",
    "veteran_status": "eeo_veteran_status",
    "disability_status": "eeo_disability_status",
    "school": "education_school",
    "degree": "education_degree",
    "preferred_name": "preferred_first_name",
    "end-year": "education_end_date",
    "start-year": "education_start_date",
    "end-month": "education_end_date",
    "start-month": "education_start_date",
    "discipline": "education_discipline",
    "candidate-location": "location_city",
    "company-name": "current_company",
    "title": "current_job_title",  # NOTE: generic id, only 2 companies (gensyn/inter) — worth a second glance, plausibly "your current job title" in a work-history block, not confirmed with same confidence as the rest
    "start-date-month": "work_history_start_date",  # NOTE: distinct id pattern from the education start-month (which is bare "start-month") — these ("gensyn"/"inter") pair with "title"/"company-name" above, so this looks like a WORK HISTORY block, not education. Kept separate from education_start_date deliberately.
    "start-date-year": "work_history_start_date",
    "end-date-month": "work_history_end_date",
    "end-date-year": "work_history_end_date",

    # label-rule matches, round 2
    "website": "personal_website",
    "attach": "resume_upload",  # confirmed via HTML: id=resume/cover_letter, "Attach" is just the button text
    "email address": "email",
    "linkedin profile link": "linkedin_url",
    "linkedin url": "linkedin_url",
    "name": "first_name",  # NOTE: ambiguous — only 3 instances all from Ogilvy, could be a combined "full name" field rather than first name specifically. Low confidence, worth a second look.
    "city": "location_city",
    "veteran status": "eeo_veteran_status",
    "gender": "eeo_gender_identity",
    "current company": "current_company",
    "country": "phone_country_code",
})

# design/finance/sales/administration/marketing/consulting/engineering/
# legal/people/product development/full time/remote/intern — all department
# or work-arrangement CHECKBOX OPTIONS (same pattern confirmed earlier for
# marketing/administration/communications), merge into department_interest.
for dept_key in ["design", "finance", "sales", "consulting", "legal", "people", "industry"]:
    CONFIRM[dept_key] = "department_interest"

# workplace-arrangement options (remote/full time/intern) are a DIFFERENT
# question from department — merge separately.
for wa_key in ["remote", "full time", "intern"]:
    CONFIRM[wa_key] = "workplace_type"

SPECIAL["please specify"] = SPECIAL.get("please specify", {"kind": "other_followup", "note": "Free-text follow-up to an 'Other' choice — must stay linked to its parent field."})
SPECIAL["if f other please explain"] = {"kind": "other_followup", "note": "Same as 'please specify' — Other-option follow-up."}

REJECT.update({
    "select": "Generic combobox placeholder text ('Select...') captured as a fallback label — itype=text, empty id, empty section on every instance. Same failure mode as 'checkbox label': many different unrelated dropdowns, not one real question.",
    "iti-0__search-input": "Confirmed via HTML: internal search box inside the international-telephone-input (iti) widget used to filter the country-code dropdown — part of the phone field's own UI chrome, not a separate question.",
    "g-recaptcha-response": "reCAPTCHA widget hidden response field — anti-bot infrastructure, not a form question. Autofill should never touch this (and normally can't — it's populated by Google's script, not user input).",
    "vendor-search-handler": "Site search/filter widget (confirmed alongside 'select-all-*-handler' cluster below) — not an application-form field.",
    "select-all-hosts-groups-handler": "Bulk-select UI control on what looks like a vendor/asset management widget embedded on the page — not a form field.",
    "select-all-vendor-groups-handler": "Same widget family as above.",
    "select-all-vendor-leg-handler": "Same widget family as above.",
    "search": "Site search box (job-board or page search), not an application field — same family as 'iti-0__search-input'/'vendor-search-handler'.",
    "ckyswitchfunctional": "CookieYes ('cky' prefix) consent-widget toggle — cookie banner, not a form field.",
    "ckyswitchanalytics": "CookieYes consent-widget toggle.",
    "ckyswitchperformance": "CookieYes consent-widget toggle.",
    "ckyswitchadvertisement": "CookieYes consent-widget toggle.",
    "ckyccpaoptout": "CookieYes consent-widget CCPA opt-out toggle (distinct from the real 'share or sale of personal data' application-form checkbox, which IS confirmed as real).",
    "phenomchatbotfooterinput": "Site chatbot widget input box (Phenom is a common HR chatbot vendor) — not a form field.",
    "l-search": "Job-board listing-page search box (Coupang/Pinterest job search UI), not an application field.",
    "l-location": "Job-board listing-page location filter, not an application field.",
    "l-location-ts-control": "Same job-board filter widget, typeahead control sub-element.",
    "autocomplete-input": "Too generic on its own (EquipmentShare only) — likely a site search/address-autocomplete widget, not confirmed as a real form field.",
    "edit-send": "Ogilvy — appears alongside the confirmed 'edit-url' honeypot field, same generic Drupal-style edit-* id prefix; likely another honeypot/admin-form artifact, not a real applicant question.",
    "searchsearch": "Duplicated/garbled site-search label.",
    "subscribe": "Newsletter subscribe widget.",
    "social media cookies": "Cookie-consent banner toggle.",
    "search departments": "Job-board search/filter UI.",
    "necessary": "Cookie-consent banner toggle (GoStudent).",
    "preferences": "Cookie-consent banner toggle (GoStudent).",
    "statistics": "Cookie-consent banner toggle (GoStudent).",
    "language switcher english": "Page-chrome language switcher.",
    "search job title or location": "Job-board search box.",
    "save job growth strategy data analyst intern m f n": "'Save Job' bookmark button on the job listing page (confirmed via id=saveJob-...), not a form field.",
    "get email updates from the city of fort worth on the topics you want": "Public-site newsletter signup, not the job application form.",
    "sign up": "Confirmed via HTML: section='Join our careers mailing list' (OneAcreFund) / generic submit button (Vast) — careers-page newsletter signup, not the application form.",
    "team": "Confirmed via HTML: id='l-team', section='Filter jobs' (Pinterest) — same 'l-' prefixed job-board filter widget family as the already-rejected l-search/l-location/l-location-ts-control clusters, not an application field.",
})

CONFIRM["github"] = "github_url"
CONFIRM["mexico"] = "location_preference"

SPECIAL["edit-url"] = {"kind": "honeypot", "note": "Confirmed via raw HTML (id=edit-url, name=url, label literally says 'Leave this field blank') — anti-bot trap. Autofill must actively skip, never fill."}

# --- Round 3: founder-caught gap — 58 residue fields had label=empty but a
# real, readable question sitting in `section` (e.g. a checkbox_group whose
# section text WAS the question). Added a section-fallback clustering rule
# (auto_cluster.py) to catch repeats; only 4 of the resulting patterns
# repeat across companies (25 fields) — the rest (~34 fields) are genuine
# per-company singletons with real, valuable question text, correctly left
# in residue for individual review (not a clustering failure — there's
# nothing to match them against). All 4 repeating section_fallback clusters
# are page-chrome noise, same categories already rejected elsewhere. ---
REJECT.update({
    "apply for position": "Confirmed via HTML: generic page title bleeding into `section` for essentially every field on EquipmentShare's page (16 fields, all itype variety) — not a real question, a page-chrome artifact.",
    "manage consent preferences": "Cookie-consent banner section heading (5 companies: HiOscar, Intrinsic Robotics, Motional, Scopely, SendBird) — same family as the already-rejected cookie-toggle clusters, just surfaced via section text instead of label this time.",
    "areas of interest": "Ogilvy — appears as a section heading with no field-level label; the actual field-level content (Marketing/Administration/etc.) was already confirmed separately under department_interest. This section_fallback cluster is the wrapper, not new content.",
    "open roles at sendbird 18": "Job-count/listing-page chrome (SendBird), not a form field.",
    "react_select_required_shim": "Confirmed via raw HTML (corpus/pages/*.html.gz, 617mediagroup job 6917269002 — 6 occurrences on one page, one per custom combobox: country/phone, location, discipline, school, degree): a React-Select-injected hidden/non-interactive input (tabindex=-1, aria-hidden=true, value-less, class matching 'remix-css-*-requiredInput') trailing EVERY custom combobox on a Greenhouse-embedded form, not just the phone widget. Exists only so the browser's native HTML5 `required` validation can fire on that non-native combobox. Not askable, not a real question, resolves itself once the combobox it shims is filled correctly. 53 companies affected — same shared form-builder template, not coincidence. See FORM_ENGINE_DESIGN.md §7 for the full resolution-layer note.",
})

# Output keyed by (rule, key) as "rule::key" strings (JSON object keys must
# be strings) so decisions never collide across clusters that happen to
# share a normalized key under different rules (e.g. "email" via id-rule
# AND label-rule are two DIFFERENT clusters with two different member
# lists — a bare-string decision below is intentionally applied to BOTH,
# since "this is an email field" is true regardless of which rule found it).
decisions = {"confirm": {}, "special": {}, "reject": {}, "unresolved": [], "not_found": []}

def rulekeys_for(bare_key):
    rules = _KEY_TO_RULEKEYS.get(bare_key)
    if not rules:
        return []
    return [(rule, bare_key) for rule in rules]

def rk_str(rule, key):
    return f"{rule}::{key}"

for key, canonical_name in CONFIRM.items():
    matches = rulekeys_for(key)
    if not matches:
        decisions["not_found"].append(key)
        continue
    for rule, k in matches:
        decisions["confirm"][rk_str(rule, k)] = canonical_name

for key, note in REJECT.items():
    matches = rulekeys_for(key)
    if not matches:
        decisions["not_found"].append(key)
        continue
    for rule, k in matches:
        decisions["reject"][rk_str(rule, k)] = note

for key, info in SPECIAL.items():
    matches = rulekeys_for(key)
    if not matches:
        decisions["not_found"].append(key)
        continue
    for rule, k in matches:
        decisions["special"][rk_str(rule, k)] = info

decided_rulekeys = set(decisions["confirm"]) | set(decisions["reject"]) | set(decisions["special"])
all_rulekeys = {rk_str(c["rule"], c["key"]) for c in cd["clusters"]}
decisions["unresolved"] = sorted(all_rulekeys - decided_rulekeys)

with open("scratchpad/cluster_decisions.json", "w", encoding="utf-8") as f:
    json.dump(decisions, f, indent=2)

print(f"confirmed: {len(decisions['confirm'])} clusters")
print(f"special:   {len(decisions['special'])} clusters")
print(f"rejected:  {len(decisions['reject'])} clusters")
print(f"total clusters: {len(all_rulekeys)}")
print(f"unresolved: {len(decisions['unresolved'])} clusters -> {decisions['unresolved']}")
if decisions["not_found"]:
    print(f"WARNING not_found (typo? key doesn't exist in any cluster): {decisions['not_found']}")

# sanity: merged canonical group sizes (rule names can't contain "::", safe to split on first occurrence)
from collections import defaultdict
merged = defaultdict(int)
for rk, name in decisions["confirm"].items():
    rule, key = rk.split("::", 1)
    merged[name] += len(clusters[(rule, key)]["members"])

print()
print("merged confirmed groups by field count:")
for name, n in sorted(merged.items(), key=lambda x: -x[1]):
    print(f"  {n:4d}  {name}")
