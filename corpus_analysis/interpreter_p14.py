"""P1.4/P1.5 — the real multi-signal interpreter (Python implementation).

This is ONE of two implementations of corpus_analysis/INTERPRETER_SPEC.md
— the other is extension/filler_utils.js's classifyField() (JS runtime).
Read that spec doc first; it's the source of truth for tier order, matching
rules, and confidence values. This file must satisfy it, but is not itself
the spec — a later spec change requires updating BOTH implementations and
re-verifying they agree (see INTERPRETER_SPEC.md's own framing for why this
split exists: treating either implementation as "the real one" that the
other gets "ported" from left no natural trigger to keep them in sync).

Per FORM_ENGINE_DESIGN.md §3.2, interpret(field) is a pure function (no DOM,
no globals, no network) walking a tiered priority chain:

    autocomplete > id > label > placeholder > nearby_text/section

Each tier is tried in order; the first tier that resolves the field wins.
Confidence reflects HOW TRUSTWORTHY THE SIGNAL TYPE generally is (which
tier resolved it), NOT a calibrated probability that this specific
prediction is correct — a tier-1 (autocomplete) match can still be wrong,
a tier-5 (nearby-text) match can still be right. Real calibration needs
live telemetry (§3.6, "Later — confidence calibration"), which doesn't
exist yet; these are placeholder per-tier numbers.

interpret() emits categories in resolveValue()'s CAPABILITY vocabulary
(extension/filler_utils.js), not taxonomy_v1's ontology vocabulary — see
category_mapping.py's module docstring for the full reasoning.

Tiers 1 (autocomplete) and 2 (id) are SELF-CONTAINED fixed lookup tables
(_AUTOCOMPLETE_TO_CAPABILITY, _ID_PATTERN_TO_CAPABILITY below), matching
INTERPRETER_SPEC.md's tables exactly — NOT a lookup against
cluster_decisions_v2.json via ground_truth_lookup(). An earlier version of
this file did call ground_truth_lookup() for these tiers (reusing
interpreter_baseline.py's offline corpus-answer-key lookup); that approach
was dropped while writing the spec doc because a live JS runtime has no
portable equivalent to a 275KB offline answer-key file — the spec's
tables are hand-written and small specifically so BOTH implementations can
carry them verbatim.

Tier 3 (label) still speaks resolveValue's vocabulary directly via
_FIELD_PATTERNS (itself originally ported FROM extension/filler_utils.js,
now the shared reference both implementations must carry the same 5
corpus-verified negative-guard fixes for — see INTERPRETER_SPEC.md's tier
3 section). Corpus-derived label additions beyond _FIELD_PATTERNS reason in
ontology terms and get translated via category_mapping.capability_for().

Structural patterns (honeypot, other_followup, react_select_required_shim,
hidden_tracking_field, hidden_non_interactive_field) are NOT topic
categories — detect_structural_pattern() runs first and short-circuits
normal interpretation, returning an `action` instead of a `category`
(FORM_ENGINE_DESIGN.md §7 / taxonomy_v1.STRUCTURAL_PATTERNS).

interpreter_baseline.py is NOT modified or replaced by this file — it stays
the frozen day-zero reference `replay.py` can always re-run for comparison.
"""

import re

from category_mapping import capability_for
from interpreter_baseline import _is_react_select_shim

# --- Confidence per tier. Placeholder numbers, not calibrated — see module
# docstring. Represents trust in the SIGNAL TYPE, not per-prediction
# correctness probability.
_TIER_CONFIDENCE = {
    "autocomplete": 0.95,
    "id": 0.9,
    "label": 0.8,
    "placeholder": 0.6,
    "section": 0.4,
    "nearby_text": 0.35,
}

# ============================================================================
# Structural pattern detection (checked FIRST, short-circuits tiers below)
# ============================================================================

_HIDDEN_TRACKING_ID_STEMS = {
    "gclid", "ft_source", "ft_campaign", "lt_source", "lead_source", "gaclientid",
}

_HONEYPOT_LABEL_MARKERS = re.compile(r"leave this field blank", re.I)
_OTHER_FOLLOWUP_LABEL = re.compile(
    r"^(if (you selected |applicable,? )?other,?\s*(above,?\s*)?please (specify|explain|elaborate)"
    r"|if (yes|applicable),?\s*please (explain|list|describe))",
    re.I,
)


def detect_structural_pattern(field):
    """Returns {"action": str, "confidence": float, "pattern": str} if
    `field` matches a known structural (non-topic) pattern, else None.
    """
    label = (field.get("label") or "").strip()
    field_id = (field.get("id") or "").strip().lower()
    itype = field.get("itype")

    # honeypot — anti-bot trap, confirmed via id + label instruction text
    # (corpus_analysis/README.md: id=edit-url, label literally instructs
    # "leave this field blank").
    if field_id == "edit-url" or _HONEYPOT_LABEL_MARKERS.search(label):
        return {"action": "skip", "confidence": 1.0, "pattern": "honeypot"}

    # hidden fields, generally. itype=hidden inputs are never user-facing —
    # not askable, not fillable, regardless of what their `label` field
    # contains. Checked BEFORE any label-based tier below because of a real
    # extraction-artifact bug found during this pass: 76,631 of 80,635
    # hidden fields (mostly Greenhouse's internal gh_jid/gh_title metadata
    # inputs) have their `label` populated with the ENTIRE surrounding page
    # text by a broken "preceding-text" label-extraction strategy — e.g. a
    # hidden gh_jid field's label containing a multi-paragraph OFCCP
    # disability-disclosure block verbatim. Left unguarded, tier 3's
    # regex-over-label search finds spurious substring matches inside that
    # huge blob (confirmed: 4,120 fields wrongly classified as `portfolio`
    # this way — the word "website" appears somewhere in the glued-together
    # page text, not because the field is actually asking about a website).
    # This is an extraction-layer bug (label-strategy fallback shouldn't be
    # gluing whole-page text onto hidden, non-interactive fields at all),
    # but interpretation must defend against it here rather than trust the
    # signal, per FORM_ENGINE_DESIGN.md standing rule §1.2 ("if a signal is
    # missing [or bad], the fix goes in extraction... [interpretation]
    # touches the DOM mechanically only") — flagging for a future
    # extraction-side fix (P1.1/corpus harvester), not silently working
    # around it by hand-tuning tier 3's regexes to dodge this one blob.
    if itype == "hidden":
        stem = re.sub(r"[-_]{1,2}\d+$", "", field_id)
        pattern = ("hidden_tracking_field"
                   if (stem in _HIDDEN_TRACKING_ID_STEMS or any(t in field_id for t in _HIDDEN_TRACKING_ID_STEMS))
                   else "hidden_non_interactive_field")
        return {"action": "skip", "confidence": 0.9, "pattern": pattern}

    # react_select_required_shim — hidden required-input trailing a custom
    # combobox, resolves itself once the combobox it shims is filled.
    if _is_react_select_shim(field):
        return {"action": "self_resolves", "confidence": 0.9, "pattern": "react_select_required_shim"}

    # other_followup — free-text follow-up to a preceding "Other" choice;
    # the field's own label carries no information, resolve from the
    # nearest preceding field instead (FORM_ENGINE_DESIGN.md §7).
    if label and _OTHER_FOLLOWUP_LABEL.search(label):
        return {"action": "resolve_from_preceding_field", "confidence": 0.85, "pattern": "other_followup"}

    return None


# ============================================================================
# Tier 3 — label patterns. Ported from extension/filler_utils.js's
# FIELD_PATTERNS (lines 113-229), which already speaks resolveValue's
# capability vocabulary directly (its keys ARE resolveValue category
# names) — no category_mapping.py translation needed for this tier.
#
# Extended beyond the live FIELD_PATTERNS with additional label phrasing
# the corpus's confirmed ontology categories revealed but FIELD_PATTERNS
# didn't cover (see the "corpus-derived additions" block below) — each
# addition mapped through category_mapping.py like any other ontology
# source, since it originates from taxonomy_v1's categories, not from
# reading filler_utils.js.
# ============================================================================

_FIELD_PATTERNS = {
    "first_name":               {"patterns": [r"first.?name", r"given.?name"],
                                  "neg": [r"last", r"preferred", r"emergency", r"reference"]},
    "last_name":                {"patterns": [r"last.?name", r"surname", r"family.?name"],
                                  "neg": [r"first", r"emergency", r"reference"]},
    "full_name":                {"patterns": [r"^name$", r"full.?name", r"your name"],
                                  "neg": [r"first", r"last", r"preferred", r"company"]},
    "email":                    {"patterns": [r"e-?mail"],
                                  # sms/whatsapp/newsletter/recruitment notif/job openings
                                  # guards: corpus-verified — consent_sms_communication and
                                  # marketing_communications_optin labels routinely mention
                                  # "email" as one channel among several. Zero real
                                  # email-capability fields mention these terms.
                                  # gdpr/controller of personal data guards: corpus-verified —
                                  # long GDPR-notice legal text mentions "email" incidentally.
                                  "neg": [r"confirm", r"emergency", r"reference",
                                          r"sms", r"whatsapp", r"newsletter",
                                          r"recruitment notif", r"job openings",
                                          r"gdpr", r"controller of personal data"]},
    "phone":                    {"patterns": [r"\bphone\b", r"mobile", r"\btel\b"],
                                  # word-boundary added to phone: unbounded, it matched
                                  # the substring in "phonetic" (live-test-verified,
                                  # Myriad360 job 8646163002 — "preferred name/nickname...
                                  # phonetic pronunciation" wrongly classified as phone
                                  # since phone is checked before preferred_name and
                                  # this tier is first-match-wins). Ported from the same
                                  # fix in extension/filler_utils.js's FIELD_PATTERNS per
                                  # INTERPRETER_SPEC.md's shared-table requirement.
                                  # sms/whatsapp guard: corpus-verified — consent_sms_communication
                                  # labels mention "phone" as one contact channel among several.
                                  "neg": [r"emergency", r"fax", r"reference", r"sms", r"whatsapp"]},
    "linkedin":                 {"patterns": [r"linked.?in"]},
    "github":                   {"patterns": [r"git.?hub"]},
    "portfolio":                {"patterns": [r"portfolio", r"personal.?site", r"\bwebsite\b"],
                                  "neg": [r"company", r"employer"]},
    "location_city":            {"patterns": [r"\bcity\b", r"\btown\b"],
                                  "neg": [r"country", r"state", r"zip", r"postal"]},
    "location_state":           {"patterns": [r"\bstate\b", r"\bprovince\b"],
                                  # 'government'/'employee' guard added during P1.4's own
                                  # replay-driven verification: "were you an employee of...
                                  # any STATE or local government" legitimately matches
                                  # \bstate\b but is a previously_employed_here question,
                                  # not a location question — found as the #3 confusion
                                  # pair (1,191 fields). Confirmed via the corpus that
                                  # zero real location_state ground-truth fields mention
                                  # government/employee language.
                                  "neg": [r"country", r"city", r"zip", r"government", r"employee"]},
    "location_country":         {"patterns": [r"\bcountry\b"],
                                  # 'authoriz'/'eligib'/'legally' guard added during P1.4's
                                  # own replay-driven verification: "are you authorized
                                  # to work IN THE COUNTRY you reside" legitimately
                                  # contains "country" but is a work_authorized question,
                                  # not a location question — found as the #1 confusion
                                  # pair (2,373 fields) in replay's confusion matrix.
                                  # Confirmed via the corpus that zero real
                                  # location_country ground-truth fields mention
                                  # authorization language, so this guard is safe.
                                  # 'sponsor' guard added in the same pass: "will you
                                  # require sponsorship... in the country for which this
                                  # role is based" matches \bcountry\b but is a
                                  # needs_sponsorship question (864 fields). Confirmed
                                  # zero real location_country fields mention sponsorship.
                                  "neg": [r"city", r"state", r"authoriz", r"eligib", r"legally", r"sponsor"]},
    "location_address":         {"patterns": [r"street.?address", r"\baddress\b"],
                                  # sms guard: corpus-verified — consent_sms_communication labels
                                  # mention "email address" describing contact channels.
                                  "neg": [r"city", r"state", r"country", r"zip", r"sms"]},
    "location_zip":             {"patterns": [r"\bzip\b", r"postal.?code"]},
    "preferred_name":           {"patterns": [r"preferred.{0,10}name", r"goes.?by", r"nickname"]},
    "pronouns":                 {"patterns": [r"pronoun"]},

    "work_authorized":          {"patterns": [r"legally authorized", r"authorized to work",
                                               r"eligible to work", r"right to work",
                                               r"permitted to work", r"us citizen or.*green card",
                                               r"citizen or permanent"],
                                  "neg": [r"sponsor", r"explain", r"detail", r"describe",
                                          r"status", r"type", r"visa", r"long.?term",
                                          r"without sponsorship", r"permanent"]},
    "work_authorized_longterm": {"patterns": [r"long.?term", r"without sponsorship",
                                               r"permanent.*auth", r"eligible.*long",
                                               r"work.*without.*requiring",
                                               r"citizen or permanent resident"],
                                  # 'disab'/'impairment'/'health condition' guard added
                                  # during P1.5's spec-compliance rewrite verification:
                                  # "do you have a disability... or LONG-TERM health
                                  # condition" legitimately matches "long.?term" but is an
                                  # eeo_disability question, not a work-authorization
                                  # question (248 fields, surfaced only after narrowing
                                  # tiers 1-2 to spec-portable lookups routed more fields
                                  # through the label tier). Confirmed zero real
                                  # work_authorized_longterm fields mention
                                  # disability/impairment/health-condition language.
                                  "neg": [r"sponsor.*require", r"explain", r"detail", r"describe",
                                          r"disab", r"impairment", r"health condition"]},
    "needs_sponsorship":        {"patterns": [r"require.*sponsor", r"need.*sponsor",
                                               r"visa sponsor", r"immigration support",
                                               r"immigration assistance", r"work authorization support",
                                               r"now or in the future.*sponsor",
                                               r"sponsor.*now or in the future"],
                                  # 'status'/'type' REMOVED from neg during P1.5's
                                  # spec-compliance verification: real needs_sponsorship
                                  # questions routinely explain sponsorship using phrasing
                                  # like "...require sponsorship for employment VISA
                                  # STATUS (e.g., H-1B visa STATUS)" — the word "status"
                                  # appears as part of describing what sponsorship means,
                                  # not because the question is asking about status.
                                  # These guards were over-blocking 2,732 of 8,787 real
                                  # needs_sponsorship fields (31%). Confirmed via the
                                  # corpus that removing them causes zero new confusion
                                  # with visa_status (checked: no real visa_status field
                                  # matches needs_sponsorship's positive patterns, so
                                  # visa_status doesn't need this guard to stay
                                  # distinguishable).
                                  "neg": [r"explain", r"detail", r"describe", r"list"]},
    "visa_status":               {"patterns": [r"visa status", r"work authorization status",
                                               r"immigration status", r"current.*visa",
                                               r"type of.*visa", r"type of.*authorization",
                                               r"work auth.*type"],
                                  # 'now or in the future'/'will you require sponsorship'
                                  # guard added during P1.4's own replay-driven
                                  # verification: "will you now or in the future require
                                  # sponsorship for employment visa status" legitimately
                                  # matches "visa status" but is a needs_sponsorship
                                  # question, not a visa_status question — found as the
                                  # #2 confusion pair (2,209 fields). Confirmed via the
                                  # corpus that real visa_status ground-truth fields never
                                  # contain this sponsorship-request phrasing.
                                  "neg": [r"now or in the future", r"will you require", r"require.*sponsor"]},
    "immigration_explanation":  {"patterns": [r"explain.*work auth", r"describe.*visa",
                                               r"detail.*immigration", r"work authorization.*detail",
                                               r"please (explain|describe).*(auth|visa|immigration)",
                                               r"additional.*immigration", r"immigration.*information",
                                               r"immigration support.*if yes",
                                               r"if yes.*please list",
                                               r"need.*immigration support.*detail"]},

    "eeo_gender":                {"patterns": [r"\bgender\b", r"gender identity"],
                                  "neg": [r"race", r"ethnicity", r"veteran", r"disability"]},
    "eeo_race":                  {"patterns": [r"\brace\b", r"racial", r"ethnicity", r"identify your race"],
                                  "neg": [r"gender", r"veteran", r"disability", r"hispanic"]},
    "eeo_hispanic":              {"patterns": [r"hispanic", r"latino"]},
    "eeo_veteran":               {"patterns": [r"veteran", r"military", r"armed forces", r"protected veteran"],
                                  # 'government'/'civilian' guard added during P1.4's own
                                  # replay-driven verification: "are you a current or
                                  # former civilian OR MILITARY employee of the US
                                  # Government" legitimately matches "military" but is a
                                  # federal-prior-employment disclosure question, not an
                                  # EEO veteran-status question — found as the #1
                                  # confusion pair after the location_state fix (1,412
                                  # fields). Confirmed via the corpus that zero real
                                  # eeo_veteran ground-truth fields mention
                                  # government/civilian language.
                                  "neg": [r"disability", r"gender", r"government", r"civilian"]},
    "eeo_disability":            {"patterns": [r"disability", r"disabled", r"disability status"],
                                  "neg": [r"veteran", r"gender"]},

    "school":                    {"patterns": [r"\bschool\b", r"\buniversity\b", r"\bcollege\b",
                                               r"institution", r"alma mater"],
                                  "neg": [r"degree", r"major", r"gpa", r"high school"]},
    "degree":                    {"patterns": [r"\bdegree\b", r"degree type", r"level of education",
                                               r"highest.*education", r"education level"],
                                  "neg": [r"school", r"major", r"field", r"discipline"]},
    "major":                     {"patterns": [r"\bmajor\b", r"field of study", r"\bdiscipline\b",
                                               r"concentration", r"area of study"],
                                  "neg": [r"school", r"degree"]},
    "gpa":                       {"patterns": [r"\bgpa\b", r"grade point", r"cumulative.*grade"]},
    "graduation_date":           {"patterns": [r"graduation", r"grad.?date", r"expected.*grad",
                                               r"end date", r"completion date", r"graduate.*when"]},

    "compensation":              {"patterns": [r"compensation", r"\bsalary\b", r"\bpay\b",
                                               r"hourly", r"\bwage\b", r"pay expectation"],
                                  "neg": [r"equity", r"bonus", r"benefit"]},
    "start_date":                {"patterns": [r"when can you start", r"available to start",
                                               r"start date", r"earliest.*start"],
                                  "neg": [r"internship", r"term"]},
    "years_experience":          {"patterns": [r"years.*experience", r"experience.*years",
                                               r"how many years"]},
    "internship_duration":       {"patterns": [r"how long.*internship", r"internship.*duration",
                                               r"internship.*length", r"length.*internship"]},
    "internship_start":          {"patterns": [r"start.*internship", r"internship.*start",
                                               r"when.*start.*intern", r"term.*start",
                                               r"internship.*term"]},
    "internship_field":          {"patterns": [r"^what field.*internship", r"^internship.*field",
                                               r"^area.*internship", r"^internship.*area"]},
    "previously_employed":       {"patterns": [r"previously employed", r"worked (here|with us|for us)",
                                               r"former.*employee", r"worked for.*company",
                                               # added during P1.5 verification: "have you
                                               # ever... been employed by <Company>" is a
                                               # very common real phrasing (3,021 corpus
                                               # fields) the original patterns above never
                                               # covered. Confirmed via corpus this only
                                               # ever matches previously_employed/
                                               # previously_employed_here fields, no
                                               # collisions with any other category.
                                               r"ever.*(been employed|worked)"]},
    "referral":                  {"patterns": [r"who referred", r"\breferral\b", r"referred by"],
                                  "neg": [r"hear about", r"learn about"]},
    "cover_letter":               {"patterns": [r"cover.?letter"]},

    "transcript_undergrad":      {"patterns": [r"undergrad(uate)?.*transcript",
                                               r"transcript.*undergrad(uate)?",
                                               r"unofficial.*transcript",
                                               r"^transcript$"],
                                  "neg": [r"grad(uate)?(?!.*under)"]},
    "transcript_grad":           {"patterns": [r"grad(uate)?.*transcript",
                                               r"transcript.*grad(uate)?",
                                               r"graduate.*transcript"],
                                  "neg": [r"undergrad", r"unofficial"]},

    # Consent — SEMANTIC CLASSIFICATION ONLY, matching extension/
    # filler_utils.js's FIELD_PATTERNS byte-for-byte per
    # INTERPRETER_SPEC.md's shared-spec discipline. These 5 categories are
    # answered by extension/consent_policy.js's policy layer at runtime,
    # NOT by any resolveValue()-equivalent here — this Python
    # implementation is offline/replay-only and never fills anything, so
    # it only needs to classify correctly, same as every other category.
    # Corpus-verified: each neg guard closes a real, found collision.
    "consent_background_check": {"patterns": [r"background check", r"criminal background",
                                               r"criminal history check", r"consent.*prior employer"],
                                  # 'condition of employment...willing to submit' guard:
                                  # corpus-verified — this exact phrasing (176 instances,
                                  # single source template) is ground-truth-labeled
                                  # qualifications_confirmation, not consent_background_check.
                                  "neg": [r"condition of employment.*willing to submit"]},
    "consent_privacy_policy":    {"patterns": [r"privacy policy", r"privacy disclosure",
                                               r"use.*personal data.*recruitment",
                                               r"privacy acknowledg"],
                                  # 'consent to receive text messages' / 'personal information
                                  # of a third party' guards: corpus-verified single-source
                                  # collisions (SMS consent, nepotism disclosure).
                                  "neg": [r"consent to receive text messages",
                                          r"provide the personal information of a third party"]},
    "consent_gdpr_notice":       {"patterns": [r"\bgdpr\b", r"data protection regulation",
                                               r"controller of personal data"]},
    "consent_sms_communication": {"patterns": [r"(sms|text message|whatsapp).{0,60}(consent|allow|contact|update)",
                                               r"(consent|allow|contact|update).{0,60}(sms|text message|whatsapp)"]},
    "marketing_communications_optin": {"patterns": [r"(future recruitment|job openings|marketing|newsletter).{0,60}(email.*me|notify|subscribe)",
                                                     r"(email.*me|notify|subscribe).{0,60}(future recruitment|job openings|marketing|newsletter)"]},
}

# --- Corpus-derived additions: label phrasing found via taxonomy_v1's 97
# confirmed ontology categories that FIELD_PATTERNS doesn't cover, mapped
# through category_mapping.py like any other ontology-sourced signal.
# Conservative and small on purpose — only added where the corpus's
# open-coding pass gives clear, unambiguous label phrasing (README's
# "Not done yet" note: some category names/boundaries are still working
# names). Each maps to a capability via category_mapping.py; entries whose
# ontology category is UNSUPPORTED are skipped (nothing to emit).
_CORPUS_LABEL_ADDITIONS = {
    # (ontology_category, [patterns], [neg_patterns])
    "resume_upload": (
        [r"^resume$", r"resume.?/.?cv", r"upload.*resume", r"\bcv\b"],
        [r"cover"],
    ),
    "how_heard_about_role": (
        [r"how did you (hear|learn|find out)", r"where did you (hear|learn|find out)"],
        [r"referral", r"referred by"],
    ),
    "consent_background_check": (
        [r"background check", r"background investigation"],
        [],
    ),
    "eeo_veteran_status": (
        [r"protected veteran status"],
        [],
    ),
}


def _matches_field_patterns(label, patterns_dict):
    """label: normalized-lowercase but NOT stripped of punctuation the way
    normalize_label() does — FIELD_PATTERNS' regexes rely on word
    boundaries like \\b that need the raw-ish text. Uses the raw label
    (lowercased) here, matching filler_utils.js's own approach (it tests
    classifyField's raw label string, not a stripped/normalized one).
    """
    if not label:
        return None
    text = label.lower()
    for category, spec in patterns_dict.items():
        neg = spec.get("neg", [])
        if any(re.search(p, text, re.I) for p in neg):
            continue
        if any(re.search(p, text, re.I) for p in spec["patterns"]):
            return category
    return None


def _tier_label(field):
    label = field.get("label") or ""
    if not label.strip():
        return None

    # Live FIELD_PATTERNS speaks resolveValue vocabulary directly.
    cap = _matches_field_patterns(label, _FIELD_PATTERNS)
    if cap:
        return cap

    # Corpus-derived additions speak ontology vocabulary, translate.
    text = label.lower()
    for ontology_cat, (patterns, neg) in _CORPUS_LABEL_ADDITIONS.items():
        if any(re.search(p, text, re.I) for p in neg):
            continue
        if any(re.search(p, text, re.I) for p in patterns):
            capability = capability_for(ontology_cat)
            if capability:
                return capability
    return None


# ============================================================================
# Tier 4 — placeholder fallback. New tier, not in today's live extension at
# all. Corpus finding (FORM_ENGINE_DESIGN.md §7): several real forms (Trade
# Republic, Anduril/Gem, Workato) put the actual question in `placeholder`
# while `label` is empty. Only tried when label yields nothing — reuses the
# SAME pattern tables as tier 3, just applied to a different field.
# ============================================================================

def _tier_placeholder(field):
    if (field.get("label") or "").strip():
        return None  # label tier should have been tried first; this tier
                      # only fires on the placeholder-carries-the-question gap
    placeholder = field.get("placeholder") or ""
    if not placeholder.strip():
        return None
    cap = _matches_field_patterns(placeholder, _FIELD_PATTERNS)
    if cap:
        return cap
    text = placeholder.lower()
    for ontology_cat, (patterns, neg) in _CORPUS_LABEL_ADDITIONS.items():
        if any(re.search(p, text, re.I) for p in neg):
            continue
        if any(re.search(p, text, re.I) for p in patterns):
            capability = capability_for(ontology_cat)
            if capability:
                return capability
    return None


# ============================================================================
# Tier 5 — nearby_text / section fallback. Lowest trust, last resort.
# Deliberately conservative: only fires when label AND placeholder are both
# empty, and requires a longer match to reduce false positives on generic
# chrome text (per the department_interest/location_preference false-merge
# lesson — corpus_analysis/README.md).
# ============================================================================

_MIN_FALLBACK_TEXT_LEN = 15


def _tier_section_nearby(field):
    if (field.get("label") or "").strip() or (field.get("placeholder") or "").strip():
        return None, None
    for text_source, tier_name in (("section", "section"), ("nearby", "nearby_text")):
        text = field.get(text_source) or ""
        if len(text.strip()) < _MIN_FALLBACK_TEXT_LEN:
            continue
        cap = _matches_field_patterns(text, _FIELD_PATTERNS)
        if cap:
            return cap, tier_name
    return None, None


# ============================================================================
# Tiers 1-2 — autocomplete, id. Per INTERPRETER_SPEC.md v1: BOTH tiers are
# self-contained fixed lookups here, matching the spec's tables exactly —
# NOT a call into ground_truth_lookup()/cluster_decisions_v2.json.
#
# An earlier version of this file DID call ground_truth_lookup() for these
# two tiers, reusing interpreter_baseline.py's offline corpus-answer-key
# lookup. That was flagged as a real spec-compliance gap while writing
# INTERPRETER_SPEC.md (P1.5): a live JS runtime has no equivalent to a
# 275KB cluster_decisions_v2.json lookup table, so a "port" of that
# approach into the browser was never going to be possible. Both
# implementations now use the SAME small, portable, hand-written tables
# below (copied verbatim from INTERPRETER_SPEC.md) — kept in sync with the
# spec doc explicitly, not derived from cluster_decisions_v2.json anymore.
# ============================================================================

_AUTOCOMPLETE_TO_CAPABILITY = {
    "given-name": "first_name",
    "family-name": "last_name",
    "name": "full_name",
    "nickname": "preferred_name",
    "email": "email",
    "tel": "phone",
    "tel-national": "phone",
    "tel-country-code": "phone",
    "tel-area-code": "phone",
    "tel-local": "phone",
    "street-address": "location_address",
    "address-line1": "location_address",
    "address-line2": "location_address",
    "address-level1": "location_state",
    "address-level2": "location_city",
    "postal-code": "location_zip",
    "country": "location_country",
    "country-name": "location_country",
    "url": "portfolio",
    # "organization" deliberately omitted — the closest ontology category
    # (current_company) is UNSUPPORTED per category_mapping.py, no live
    # capability exists to emit.
}


def _tier_autocomplete(field):
    ac = (field.get("ac") or "").strip().lower()
    return _AUTOCOMPLETE_TO_CAPABILITY.get(ac)


# id patterns per INTERPRETER_SPEC.md's tier 2 table — small, hand-written,
# auditable. Checked as a case-insensitive substring against the id after
# stripping a trailing "-N"/"_N" suffix (same suffix-stripping convention
# as normalize_id(), reused here for consistency, not because this tier
# depends on normalize_id()'s denylist behavior).
_ID_PATTERN_TO_CAPABILITY = [
    (re.compile(r"first_?name|fname", re.I), "first_name"),
    (re.compile(r"last_?name|lname", re.I), "last_name"),
    (re.compile(r"email", re.I), "email"),
    (re.compile(r"phone|mobile", re.I), "phone"),
    (re.compile(r"linkedin", re.I), "linkedin"),
    (re.compile(r"github", re.I), "github"),
    # id='cover_letter' added during P1.5's spec-compliance verification —
    # 10,718 fields have literally id="cover_letter" but label text that's
    # either non-informative ("Attach") or non-English ("파일 첨부",
    # "Anhängen" — a file-upload button's own localized text, not the
    # question), so tier 3 (label) can never catch these; the id IS the
    # only reliable signal. Note this is deliberately checked AFTER the
    # tighter patterns above (github before this) since 'cover_letter'
    # would not otherwise collide with them.
    (re.compile(r"cover_?letter", re.I), "cover_letter"),
]


def _tier_id(field):
    field_id = field.get("id") or ""
    if not field_id:
        return None
    stem = re.sub(r"[-_]{1,2}\d+$", "", field_id.strip())
    for pattern, capability in _ID_PATTERN_TO_CAPABILITY:
        if pattern.search(stem):
            return capability
    return None


# ============================================================================
# Main entry point
# ============================================================================

def interpret(field):
    """Returns {"category": str|None, "confidence": float, "tier": str|None,
    "action": str|None}.

    `category` is a resolveValue() capability name, or None (UNKNOWN /
    structural). `action` is set (category is None) for structural
    patterns (skip / self_resolves / resolve_from_preceding_field).
    """
    structural = detect_structural_pattern(field)
    if structural:
        return {"category": None, "confidence": structural["confidence"],
                "tier": structural["pattern"], "action": structural["action"]}

    cap = _tier_autocomplete(field)
    if cap:
        return {"category": cap, "confidence": _TIER_CONFIDENCE["autocomplete"], "tier": "autocomplete", "action": None}

    cap = _tier_id(field)
    if cap:
        return {"category": cap, "confidence": _TIER_CONFIDENCE["id"], "tier": "id", "action": None}

    cap = _tier_label(field)
    if cap:
        return {"category": cap, "confidence": _TIER_CONFIDENCE["label"], "tier": "label", "action": None}

    cap = _tier_placeholder(field)
    if cap:
        return {"category": cap, "confidence": _TIER_CONFIDENCE["placeholder"], "tier": "placeholder", "action": None}

    cap, tier_name = _tier_section_nearby(field)
    if cap:
        return {"category": cap, "confidence": _TIER_CONFIDENCE[tier_name], "tier": tier_name, "action": None}

    return {"category": None, "confidence": 0.0, "tier": None, "action": None}
