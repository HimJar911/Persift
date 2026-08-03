# Interpreter specification (v1)

Authoritative, implementation-independent statement of what `interpret(field)
-> {category, confidence, tier, action}` does. Written per P1.5's plan
(Aug 2 2026 session) after a review round flagged that treating the JS
runtime implementation as a "port" of `corpus_analysis/interpreter_p14.py`
would silently make the Python file the source of truth forever, with no
process keeping a future JS change and a future Python change in sync.
This document is the source of truth instead — both implementations satisfy
it, neither is derived from the other, and either can legitimately diverge
from the other's *code* as long as both still satisfy *this*.

**Two implementations, one spec:**
- **Python** — `corpus_analysis/interpreter_p14.py`. Offline, scored by
  `replay.py` against the 632,947-field corpus (`oc_compact_full_v2.json` +
  `cluster_decisions_v2.json`).
- **JavaScript** — `extension/filler_utils.js`'s `classifyField()`.
  Runtime, live in the browser, scored by comparing its output against the
  Python implementation's output for the same real fields (see P1.5 plan's
  Verification step 2 — direct category-string comparison per field, not
  eyeballed).

When this spec changes, both implementations need updating and
re-verified for agreement — that update is the explicit trigger this
document exists to create, replacing the implicit (and easy to forget)
expectation that "the JS should match the Python file."

## Output shape

```
{
  category:   string | null,   // a resolveValue() CAPABILITY name, or null
  confidence: float,           // trust in the SIGNAL TYPE that resolved it, NOT
                                // a calibrated per-prediction correctness probability
  tier:       string | null,   // which tier/pattern resolved it, for debugging/telemetry
  action:     string | null,   // set only for structural patterns (category is null)
}
```

**Vocabulary: `category` is always a `resolveValue()` capability name**
(`extension/filler_utils.js`'s existing ~30-category live vocabulary), never
a `taxonomy_v1` ontology category name. See `category_mapping.py`'s module
docstring for the full ontology-vs-capability reasoning — the short version:
`taxonomy_v1` answers "what is this field asking" (research), `resolveValue`
answers "what can the product currently fill" (product surface), and they
are deliberately not the same list. Any signal source that reasons in
ontology terms (corpus-derived id/label rules) must translate through
`category_mapping.capability_for()` before being returned. The browser-side
implementation never needs the ontology or the mapping table at runtime —
they're a build-time reference for authoring the JS implementation's rules,
not a live dependency.

## Structural pattern detection — runs FIRST, short-circuits everything below

Checked before any tier. If matched, `category` is `null` and `action` is
set instead — these are never topic-category answers
(`FORM_ENGINE_DESIGN.md` §7 / `taxonomy_v1.STRUCTURAL_PATTERNS`).

| Pattern | Detection rule | `action` | `confidence` |
|---|---|---|---|
| `honeypot` | field `id` is exactly `edit-url`, OR label matches `/leave this field blank/i` | `skip` | 1.0 |
| `hidden_non_interactive_field` | `itype`/`htmlType` is `hidden` and id doesn't match a known tracking-param stem | `skip` | 0.9 |
| `hidden_tracking_field` | `itype`/`htmlType` is `hidden` AND id (after stripping a trailing `-N`/`_N` suffix) is or contains one of: `gclid`, `ft_source`, `ft_campaign`, `lt_source`, `lead_source`, `gaclientid` | `skip` | 0.9 |
| `react_select_required_shim` | label is empty OR is generic placeholder chrome (`"select"`, `"select..."`, localized Korean/Japanese variants), AND placeholder is empty, AND `itype`/`htmlType` is `text`, AND `required` is true | `self_resolves` | 0.9 |
| `other_followup` | label matches `/^(if (you selected \|applicable,? )?other,?\s*(above,?\s*)?please (specify\|explain\|elaborate)\|if (yes\|applicable),?\s*please (explain\|list\|describe))/i` | `resolve_from_preceding_field` | 0.85 |

**Why the hidden-field guard matters — real bug found this session, not
theoretical:** 76,631 of 80,635 `hidden` fields in the corpus had their
`label` populated with the ENTIRE surrounding page text by a broken
label-extraction fallback strategy (a hidden Greenhouse `gh_jid` field's
label containing a full OFCCP disability-disclosure block verbatim). Any
tier that runs a regex search over `label` on a field like this will find
spurious substring matches (confirmed: 4,120 fields wrongly classified
`portfolio` because "website" appeared somewhere in the glued blob). The
hidden-field check MUST run before the label tier, unconditionally,
regardless of what `label` contains — this is a defense against a known
extraction-layer defect, not a modeling choice.

## Tier 1 — autocomplete

**Genuinely portable, no corpus dependency** — checks the field's
`autocomplete` attribute against the fixed HTML autocomplete spec token
list (`given-name`, `family-name`, `email`, `tel`, `street-address`,
`address-level1`, `address-level2`, `postal-code`, `country`,
`country-name`, `bday*`, `sex`, `organization`, `organization-title`,
`url`, `photo`, `language`, etc. — full list in
`interpreter_p14.py`'s `_AUTOCOMPLETE_SPEC_TOKENS`, copy verbatim into the
JS implementation, it's a static constant with no offline dependency).
Each spec token maps to exactly one `resolveValue` capability (e.g.
`given-name` → `first_name`, `tel` → `phone`, `address-level1` →
`location_state`) — this mapping is small and fixed, write it directly as
a JS lookup table, no `category_mapping.py` needed at runtime since these
tokens map 1:1 to capabilities already.

Confidence: **0.95**.

## Tier 2 — id (and name)

**Important divergence point, found while writing this spec — the Python
implementation's tier 2 is NOT actually portable as-is.** `interpreter_p14.py`'s
`_tier_id()` calls `ground_truth_lookup()`, which looks up the field's
normalized `id` against `cluster_decisions_v2.json` (a 275KB static
answer-key file built from the corpus). That's an offline-only dependency
— there is no equivalent live lookup table in the browser, and shipping
one would mean bundling a large, corpus-specific artifact into the
extension for a single-tier fallback, which is out of proportion to the
value.

**Resolution for this tier, decided while writing this spec:** the JS
implementation's id tier is NOT "look up this id in a table" — it's a
small set of high-confidence, directly-legible id-attribute patterns
carried over from the SAME categories `_FIELD_PATTERNS` already covers
(e.g. `id` containing `first_name`/`firstname`, `last_name`/`lastname`,
`email`, `phone`). This is a narrower, more conservative tier 2 than the
Python implementation's corpus-lookup version — intentionally, since a
hand-written id-pattern list is auditable and portable, where a giant
offline answer-key lookup is neither. Document any real id-pattern found
useful here directly in this spec table so both implementations can adopt
it, rather than letting the JS implementation invent one-off patterns not
reflected back into the spec.

| id pattern (case-insensitive substring, after stripping a trailing `-N`/`_N` suffix) | capability |
|---|---|
| `first_name`, `firstname`, `fname` | `first_name` |
| `last_name`, `lastname`, `lname` | `last_name` |
| `email` | `email` |
| `phone`, `mobile` | `phone` |
| `linkedin` | `linkedin` |
| `github` | `github` |
| `cover_letter` | `cover_letter` (added post-v1: 10,718 corpus fields have `id="cover_letter"` with non-informative or non-English label text — e.g. "Attach", "파일 첨부" — where tier 3 can never catch them; the id is the only reliable signal) |

Confidence: **0.9**.

## Tier 3 — label

The full `_FIELD_PATTERNS` table (positive + negative regex guards per
capability) — this is the SAME table in both implementations, kept
byte-identical. Both implementations carry these corpus-verified fixes
(each confirmed to cause zero false negatives against real ground-truth
fields before being added):
- `location_country` vs `work_authorized`/`needs_sponsorship` (added
  during P1.4)
- `location_state`/`eeo_veteran` vs `previously_employed_here` (P1.4)
- `visa_status` vs `needs_sponsorship` (P1.4)
- `work_authorized_longterm` vs `eeo_disability` — "long-term health
  condition" (added post-v1, during P1.5's spec-compliance rewrite)
- `needs_sponsorship`'s `status`/`type` negative guards REMOVED — were
  over-blocking 31% (2,732/8,787) of real fields (post-v1, P1.5)
- `previously_employed` extended with `ever.*(been employed|worked)` —
  3,021 corpus fields used this phrasing and were previously uncaught
  (post-v1, P1.5)

See `interpreter_p14.py`'s inline comments for each fix's full rationale
and corpus verification method.

Matching rule: strip asterisks/required-markers/trailing punctuation,
lowercase, test each capability's negative patterns first (any match →
skip this capability), then positive patterns (first match wins), in
insertion order of the table.

Confidence: **0.8**.

## Tier 4 — placeholder

Only attempted when label is empty. Same `_FIELD_PATTERNS` table, applied
to `placeholder` instead of `label`. Real corpus finding motivating this
tier (`FORM_ENGINE_DESIGN.md` §7): several real forms (Trade Republic,
Anduril/Gem, Workato) carry the actual question in `placeholder` while
`label` is empty.

Confidence: **0.6**.

## Tier 5 — section / nearby text fallback

Only attempted when BOTH label and placeholder are empty. Same
`_FIELD_PATTERNS` table, applied first to `section`, then to `nearbyText`
— each source requires at least 15 characters of text before being tried
(short fragments produce too many false positives). Deliberately the
lowest-trust tier: cross-company checkbox-group / generic chrome text
false-merges are a documented, recurring failure shape in this corpus
(`corpus_analysis/README.md`'s department_interest/location_preference
correction) — any category resolved via this tier on a `checkbox`/
`checkbox_group` field should be treated with extra suspicion, not blind
trust.

Confidence for `section`: **0.4**. Confidence for `nearbyText`: **0.35**.

## What is NOT part of this spec

- **Confidence calibration.** All numbers above are placeholders reflecting
  relative signal trust, not measured correctness probabilities — real
  calibration needs live telemetry data (`FORM_ENGINE_DESIGN.md` §3.6,
  "Later — confidence calibration"), which doesn't exist yet.
- **Fill mechanics.** This spec governs classification only —
  `category` in, nothing about how that category's value gets written into
  the DOM. See `FORM_ENGINE_DESIGN.md` §3.4 for fill/verify/retry.
- **Re-interpretation during retry.** A field is classified exactly once.
  If a fill attempt fails and gets retried, the retry never re-invokes
  `interpret()` or changes the field's assigned category — it only tries a
  different mechanical strategy for writing the SAME already-resolved
  value. See the P1.5 plan's Step 4 for the full statement of this
  invariant.
- **LLM fallback** for `essay`/low-confidence fields — explicitly deferred
  post-corpus/post-pitch (`FORM_ENGINE_DESIGN.md` §3.6).

## Version history

- **v1** (Aug 2 2026) — first version, written concurrently with the JS
  runtime implementation (P1.5). Reflects `interpreter_p14.py` as it stood
  after P1.4's confusion-matrix-driven tuning pass, with tier 2 (id)
  redefined here as a small hand-written pattern list rather than an
  offline answer-key lookup, since the latter has no portable JS
  equivalent. Both implementations updated to match and independently
  re-scored: Python via `replay.py` (88.4% coverage / 0.59% mismatch,
  improving on the pre-rewrite 87.25%/0.73%), JS via a direct offline/live
  agreement check against 360 real corpus fields across two independent
  samples (360/360 agreement — one real bug found and fixed along the way:
  the JS `react_select_required_shim` check tested the wrong field
  property, `htmlType` instead of `inputType`, and never fired until
  corrected).
