"""CORRECTION: the round-1 cluster review confirmed 'administration' /
'communications' / 'marketing' / etc. label-matched clusters as one merged
department_interest / location_preference category. Individual raw-HTML
verification (triggered by spotting d2l's 'No Department' field literally
named filter-group-1_4) proved most members are job-board FILTER widgets or
cookie-banner CONSENT toggles that happen to share the same word as a real
department name — not application-form fields at all.

Verified per-company, not assumed from pattern:
- andurilindustries: job-board filter (id='open-roles-list', "DEPARTMENT"/
  "EMPLOYMENT TYPE" headings) — CONFIRMED FAKE (fi 14-121, the non-122-130 range)
- cannondesign: job-board filter (data-filterdropdown-list, sr-only heading) — FAKE
- d2l: job-board filter (name='filter-group-1_N') — FAKE
- stripe: job-board filter (class='ControlledFilterOption') — FAKE
- gostudent: Cookiebot cookie-consent banner (CybotCookiebotDialogBody*) — FAKE
- ogilvy: general "Contact Us"/talent-network form (has contact_email +
  Interest dropdown: Employment Verification/Media Inquiries/New Business),
  NOT tied to any specific job application — FAKE
- oneacrefund: job-board filter (class='c-filter__wrapper') — FAKE
- omnicomhealth: REAL Greenhouse custom field (id='custom-field-*-label',
  <label>Department</label>) — CONFIRMED REAL
- vast: job-board filter ("Search keywords" + <option>All departments</option>) — FAKE

Anduril fi 122-130 (already confirmed real via manual_field_index_tags.py,
verified <label class='required'>Which type of role are you interested
in?</label>) are NOT touched here — they were already correctly separated
from the fake fi 14-121 range in that earlier pass.
"""

import json

with open("scratchpad/oc_compact_full.json", encoding="utf-8") as f:
    data = json.load(f)

FAKE_NOTE = (
    "CORRECTION (this session): originally merged into department_interest/"
    "location_preference by label-text match, but raw-HTML verification "
    "proved this specific field is job-board filter chrome or a cookie-"
    "consent toggle, not a real application-form field. See "
    "scratchpad/correction_department_location.py for the full per-company "
    "verification trail."
)

REAL_NOTE = (
    "Verified real via raw HTML: id='custom-field-6364019008-label', a "
    "genuine Greenhouse embedded-form <label>Department</label> — unlike "
    "vast's same-named field (job-board filter, rejected separately)."
)

# (ci, fi) pairs confirmed FAKE — job-board filter / cookie-consent noise
FAKE = [
    (7, 14), (7, 23), (7, 27), (7, 46), (7, 48),   # andurilindustries (non-122-130 range)
    (7, 67), (7, 76), (7, 107), (7, 123), (7, 124), (7, 125), (7, 129),
    (15, 9), (15, 26), (15, 32), (15, 42), (15, 13), (15, 12), (15, 15),  # cannondesign
    (26, 7), (26, 4), (26, 5), (26, 9),             # d2l
    (102, 2), (102, 9), (102, 11), (102, 24), (102, 26), (102, 31),      # stripe
    (102, 109), (102, 120), (102, 79), (102, 88), (102, 119), (102, 122),
    (41, 3), (41, 7),                                # gostudent
    (69, 41), (69, 5), (69, 6),                      # ogilvy
    (71, 10), (71, 17),                              # oneacrefund
    (110, 1),                                        # vast
]

# (ci, fi) pairs confirmed REAL
REAL = [
    (70, 4),  # omnicomhealth
]

ENTRIES = []
for ci, fi in FAKE:
    ENTRIES.append({"ci": ci, "fi": fi, "action": "reject", "category": None, "note": FAKE_NOTE})
for ci, fi in REAL:
    ENTRIES.append({"ci": ci, "fi": fi, "action": "confirm", "category": "department_interest", "note": REAL_NOTE})

# sanity check every reference resolves
bad = 0
for e in ENTRIES:
    try:
        data[e["ci"]]["fields"][e["fi"]]
    except IndexError:
        print("BAD REF:", e)
        bad += 1
print(f"bad refs: {bad} / {len(ENTRIES)}")

with open("scratchpad/correction_department_location.json", "w", encoding="utf-8") as f:
    json.dump(ENTRIES, f, indent=2)

print(f"correction entries: {len(ENTRIES)} (fake/reject: {len(FAKE)}, real/confirm: {len(REAL)})")
