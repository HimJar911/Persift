"""Manual per-field-index decisions from reading actual raw HTML context,
not just option-list text — used when a field's true nature can only be
determined by checking what actually wraps it in the DOM (e.g. Anduril's
117 checkboxes, where reading every option text alone would have wrongly
suggested they're all real application-form fields).

Each entry is keyed by (company, field_index) rather than label text, since
these decisions are specific to one company's page structure, not a
pattern expected to repeat/generalize.

Format: {"ci": <company index in oc_compact_full.json>, "fi": <field
index>, "action": "confirm"|"reject", "category": <name or None>, "note":
<evidence>}
"""

import json

with open("scratchpad/oc_compact_full.json", encoding="utf-8") as f:
    data = json.load(f)

ci_anduril = next(i for i, c in enumerate(data) if c["company"] == "andurilindustries")

ENTRIES = []

# Confirmed via raw HTML (corpus/pages/5121683007.html.gz): fields 14-61 (48
# team/product names) and 62-117 (56 locations) both live inside
# id="open-roles-list" aria-label="Open Roles Filters", headed "DEPARTMENT"
# — a job-BOARD search/filter widget for browsing open roles, NOT the
# application form. Field 118-121 (Contract/Full-time/Intern/Temporary)
# confirmed same widget family, headed "EMPLOYMENT TYPE multiselect
# dropdown". All page chrome, not real application questions.
_REJECT_RANGES = [(14, 61), (62, 117), (118, 121)]
_REJECT_NOTE = (
    "Confirmed via raw HTML: lives inside id='open-roles-list' "
    "aria-label='Open Roles Filters' — a job-BOARD search/filter widget "
    "(browse open roles by department/location/employment-type), not the "
    "application form. Distinct from field 122-130's group 4, which has a "
    "real <label class='required'> reading 'Which type of role are you "
    "interested in?' inside the actual application form."
)
for lo, hi in _REJECT_RANGES:
    for fi, f in enumerate(data[ci_anduril]["fields"]):
        if lo <= fi <= hi and f.get("itype") == "checkbox":
            ENTRIES.append({"ci": ci_anduril, "fi": fi, "action": "reject", "category": None, "note": _REJECT_NOTE})

# Confirmed real: fi 122-130, real application-form question "Which type of
# role are you interested in?" (label found in raw HTML, required=true).
_CONFIRM_NOTE = (
    "Confirmed via raw HTML: real <label class='required'> reads 'Which "
    "type of role are you interested in?' — genuine application-form "
    "question, required. Distinct from the job-board filter widget above."
)
for fi in range(122, 131):
    f = data[ci_anduril]["fields"][fi]
    if f.get("itype") == "checkbox":
        ENTRIES.append({"ci": ci_anduril, "fi": fi, "action": "confirm", "category": "department_interest", "note": _CONFIRM_NOTE})

with open("scratchpad/manual_field_index_tags.json", "w", encoding="utf-8") as f:
    json.dump(ENTRIES, f, indent=2)

rej = sum(1 for e in ENTRIES if e["action"] == "reject")
conf = sum(1 for e in ENTRIES if e["action"] == "confirm")
print(f"total entries: {len(ENTRIES)} (reject: {rej}, confirm: {conf})")
