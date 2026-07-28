"""Manual resolution of triage_real_vs_junk.py's full `uncertain` bucket (84
records) — every one read via its extracted field list / raw evidence before
being resolved, per the plan's "uncertain bucket gets hand-reviewed in full
before Step 3, not deferred indefinitely" QA gate.

Method: grouped by company/URL pattern (same company's postings share the
same page template, so one representative read generalizes to its siblings
— verified by checking that every sibling in a group has the same field
shape, not just assumed).

Findings:
- 60 records: stripe.com/jobs/search?gh_jid=... — all share identical
  ~124-125-field shape, every field a department-name checkbox_group with
  section=None, no resume field. Confirmed junk: this is Stripe's job-board
  department-filter widget (same false-positive shape as the
  department_interest/location_preference correction already documented in
  corpus_analysis/README.md), not an application form.
- 18 records across 6 companies (Ogilvy, Cannondesign, Monks, D2L,
  OneAcreFund, CityFortWorth) — each read directly: Ogilvy is a Drupal
  "edit-field-*" CRM widget page; Cannondesign/Monks/D2L/OneAcreFund are
  job-listing search/filter/newsletter-signup chrome (matches the corpus
  README's documented false-positive pattern); CityFortWorth is a
  __VIEWSTATE ASP.NET page — not even Greenhouse-rendered, a different
  platform got mis-crawled entirely. All confirmed junk.
- 6 records (Toggleai / reflexivity.firststage.co) — genuinely different
  failure mode: a single unlabeled <input type="file"> per job, no other
  fields extracted at all. Not a listing/search page (no filter chrome,
  no department checkboxes) — looks like a real but severely
  under-extracted application form on a non-standard Greenhouse embed
  (firststage.co, not the usual job-boards.greenhouse.io / boards.greenhouse.io
  domains). Does NOT cleanly fit likely_real (only one field, no label, not
  enough to classify) or likely_junk (it's not chrome/filter widgets).
  Resolution: flagged as its own bucket `extraction_gap`, logged to
  ontology_debt.md rather than forced into either bucket — matches
  FORM_ENGINE_DESIGN.md's standing rule against force-fitting ambiguous
  cases.

Run: python corpus_analysis/uncertain_bucket_resolution.py
Reads:  corpus_analysis/triage_real_vs_junk.json (for the uncertain list)
Writes: corpus_analysis/triage_real_vs_junk_resolved.json — final bucket
        assignment for every job_id across all three original buckets
        PLUS the newly-resolved uncertain records (junk / extraction_gap).
"""

import json
from pathlib import Path

BASE = Path(__file__).parent
TRIAGE = BASE / "triage_real_vs_junk.json"
OUT = BASE / "triage_real_vs_junk_resolved.json"

_JUNK_URL_PREFIXES = (
    "https://stripe.com/jobs/search",
    "https://www.ogilvy.com/careers/",
    "http://www.cannondesign.com/careers/",
    "https://www.monks.com/careers/",
    "https://www.d2l.com/careers/",
    "https://oneacrefund.org/vacancies/",
    "https://boards.greenhouse.io/cityoffortworth/",
)

_EXTRACTION_GAP_URL_PREFIX = "https://reflexivity.firststage.co/jobs"


def resolve(record):
    url = record["crawled_url"]
    if any(url.startswith(p) for p in _JUNK_URL_PREFIXES):
        return "likely_junk"
    if url.startswith(_EXTRACTION_GAP_URL_PREFIX):
        return "extraction_gap"
    raise ValueError(f"Unresolved uncertain record, needs its own read: {record}")


def main():
    with open(TRIAGE, encoding="utf-8") as f:
        d = json.load(f)

    final = {
        "likely_real": list(d["likely_real"]),
        "likely_junk": list(d["likely_junk"]),
        "extraction_gap": [],
    }

    for record in d["uncertain"]:
        outcome = resolve(record)
        final[outcome].append(record if outcome != "likely_junk" else {
            **record, "resolved_from": "uncertain"
        })

    counts = {k: len(v) for k, v in final.items()}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({**final, "counts": counts}, f, indent=2)

    print("Final counts:", counts)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
