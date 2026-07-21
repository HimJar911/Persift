"""Manual category assignments for singleton residue fields the founder
resolved by eye in chat (they're one-off phrasings, so clustering rules
structurally cannot group them with anything). Recorded as explicit
(company, job_id, field label) triples rather than bare label text, since
several of these labels don't repeat anywhere else in the corpus and a
bare-string key risks silently matching an unrelated field later if the
corpus grows.

Source: 617mediagroup open-coding discussion, this session.
"""

import json

with open("scratchpad/oc_compact_full.json", encoding="utf-8") as f:
    data = json.load(f)

# (company, exact label OR section-fallback text, canonical category, note)
ASSIGNMENTS = [
    ("617mediagroup", "Pronouns", "preferred_pronouns",
     "Same concept as the confirmed preferred_pronouns category, shorter phrasing."),
    ("617mediagroup", "Personal or Professional Website (Optional)", "personal_website",
     "NOT linkedin_url (the weak auto-guess was wrong) — same category as the confirmed 'Website' cluster. "
     "Also carries a resolution-layer rule, not just a label: if profile has no website AND this field is "
     "required, abort the application rather than submit incomplete or guess — see FORM_ENGINE_DESIGN.md §7."),
    ("617mediagroup", "Where did you hear about this job opening?", "how_heard_about_role",
     "Same concept as the confirmed how_heard_about_role category, longer phrasing."),
    ("617mediagroup", "College(s) attended, trade/vocational schools attended, university/universities attended, and/or other multi-year post-high school degree or certificate programs attended (if applicable)", "education_school",
     "Free-text variant of the confirmed education_school category (which is dropdown-based, id=school--0). "
     "Same underlying fact, different field SHAPE (text vs dropdown) — flagged for the interpreter to "
     "potentially need shape-aware handling, not assumed identical to the dropdown case."),
    ("617mediagroup", "Degree(s) or certification(s) achieved as part of multi-year, post-high school program (if applicable)", "education_degree",
     "Free-text variant of the confirmed education_degree category, same shape caveat as education_school above."),
    ("617mediagroup", "What date are you available to start your internship?", "availability_start_date",
     "Same concept as the confirmed availability_start_date category."),
    ("617mediagroup", "How many hours per week are you available?", "availability_hours_per_week",
     "NEW category — confirmed as real and distinct during this session, no existing match. First instance "
     "found; not yet validated against a second occurrence elsewhere in the corpus."),
    ("617mediagroup", None, "location_preference",
     "Section-fallback field (empty label, section='Please indicate which locations you are able work in...'). "
     "Same concept as the confirmed location_preference category — NOT work_authorized (the weak auto-guess "
     "was wrong)."),
]

out = []
matched_companies = set()
for company, label_hint, category, note in ASSIGNMENTS:
    ci = next((i for i, c in enumerate(data) if c["company"] == company), None)
    if ci is None:
        print(f"WARNING: company not found: {company}")
        continue
    found = False
    for fi, f in enumerate(data[ci]["fields"]):
        lbl = f.get("label")
        sec = f.get("section")
        if label_hint is not None and lbl == label_hint:
            found = True
        elif label_hint is None and not lbl and sec and "Please indicate which locations" in sec:
            found = True
        else:
            continue
        out.append({
            "ci": ci, "fi": fi, "company": company,
            "category": category, "note": note,
            "label_text": lbl or sec,
        })
        break
    if not found:
        print(f"WARNING: field not found for {company!r} / {label_hint!r}")

with open("scratchpad/manual_singleton_tags.json", "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)

print(f"resolved {len(out)} / {len(ASSIGNMENTS)} manual singleton tags")
for e in out:
    print(f"  {e['company']:15s} fi={e['fi']:3d}  {e['category']:30s}  {e['label_text'][:50]!r}")
