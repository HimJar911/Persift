# Consent-question policy specification

Records the category → default-answer table and the architectural
boundary it lives behind. Deliberately NOT part of `INTERPRETER_SPEC.md` —
this document is about a policy decision (what should we answer), not
interpretation (what is this field asking). Read `INTERPRETER_SPEC.md`
first if you haven't; this doc assumes that boundary is already
understood.

## Why this exists as a separate layer, not part of the interpreter

`FORM_ENGINE_DESIGN.md` §1.6 designed "auto-answer consent questions on
the user's behalf" in July 2026. It was never actually built. The second
live browser test after P1.5's live wiring (Myriad360, Greenhouse job
`8646163002`) hit a real, live consent-shaped question (a voluntary
demographic-survey opt-in combobox) that fell through unclassified,
surfacing this gap.

**A first design draft put `accept`/`decline` directly inside the
interpreter's structural-pattern detection** (the same function that
detects honeypots and hidden fields). Rejected after review, for a real
architectural reason: the interpreter answers *"what is this field
asking"* — a semantic question the corpus can validate via replay.
Consent defaults answer *"what should we do about it"* — a policy
decision the corpus has no signal for at all (it cannot tell you whether
declining was the right call for any given real user). Merging them would
have meant `replay.py` started silently scoring a mixture of semantic
accuracy and policy correctness, two orthogonal things.

**A second draft put the answer inside `resolveValue()`'s switch
statement** (the profile-lookup function). Also rejected: `resolveValue()`
means "given a category, retrieve the PROFILE value" for every existing
case (even `compensation`'s JD-range parsing is still answering "what does
the user want," derived from page content) — consent answers aren't
profile facts, they're policy defaults, a different kind of thing.

**Final design — a real 4th step in the pipeline, not new machinery
bolted onto an existing one:**

```
classifyField() / interpret()        → semantic category only (consent_sms_communication, etc.)
        ↓
category_mapping.py                  → capability name (same as any other category)
        ↓
fillField()'s dispatcher             → is this category consent-policy-backed?
        ↓                              ├─ yes → resolveConsentAnswer() (this file's logic)
        ↓                              └─ no  → resolveValue() (profile lookup, unchanged)
fillReactCombobox / fillCheckboxGroup / fillNativeSelect   → unchanged, consumes either resolver's output
        ↓
isInputFilled() / retryFill()        → unchanged, verify/retry doesn't care which resolver answered
```

## Scope — which categories, and why only these 5

Checked the corpus (`oc_compact_full_v2.json`) directly before building
anything: consent-shaped ontology categories and their real `itype`
distribution. `combobox` dominates every one — the July design's framing
("checkboxes") doesn't match real Greenhouse forms.

| Category | Real corpus combobox instances | In scope |
|---|---|---|
| `consent_attestation_general` | 6,519 | **NO** — contaminated, see below |
| `consent_privacy_policy` | 1,614 | yes |
| `consent_background_check` | 599 | yes |
| `consent_sms_communication` | 1,212 | yes |
| `marketing_communications_optin` | 412 | yes |
| `consent_gdpr_notice` | 18 | yes |
| `consent_ccpa_share_sale` | 0 confirmed instances | no — nothing to build against |
| `ccpa_california_disclosure` | 0 confirmed instances | no — nothing to build against |

**`consent_attestation_general` excluded deliberately.** Sampled its real
labels: mixed with genuine generic-attestation questions are clearly
different question types with their own dedicated categories — "Did you
graduate?" (education status), "Are you legally authorized to work in the
United States" (work authorization). Same "generic-bucket
mis-clustering" shape as the documented department_interest/
location_preference false-merge (`corpus_analysis/README.md`). Needs its
own cleanup/re-split pass before any policy-answering logic touches it.

## The default-answer table

Lives in `extension/consent_policy.js` (JS, runtime — the only
implementation that actually fills anything; the Python side,
`interpreter_p14.py`, only needs to classify, not answer, since it's
offline/replay-only). Each entry carries a `rationale`, not just a bare
default — the same discipline `category_mapping.py`'s `Mapping` dataclass
already uses, for the same reason: a bare `consent_sms: 'decline'` loses
the judgment call that makes it non-trivial.

| Category | Default | `requiredByEmployer` | Rationale |
|---|---|---|---|
| `consent_background_check` | accept | true | Declining blocks the application from proceeding — but the user could still choose to decline and abandon this application; that's a real choice, not an impossible one. |
| `consent_privacy_policy` | accept | true | Required acknowledgment to proceed, same shape as ToS. |
| `consent_gdpr_notice` | accept | true | Required data-processing acknowledgment. |
| `consent_sms_communication` | decline | false | Optional communication-channel opt-in, not required to apply — user has not opted in, so do not opt them in on their behalf. |
| `marketing_communications_optin` | decline | false | Explicitly promotional/marketing opt-in — clearly voluntary. |

**`requiredByEmployer` and `overridable` are independent fields, not one
derived from the other.** An earlier version of this table set
`overridable: false` for the 3 required-consent categories on the
assumption that "required by the employer" means "not a real user
choice." That's wrong — a user can always refuse a background check, the
consequence is simply that the application can't proceed. All 5 entries
currently have `overridable: true`, though it has no runtime effect yet
(no settings UI reads it) — it exists so a future per-user-override
extension has a real flag to check instead of re-deriving one from
`requiredByEmployer`.

## The override path (not built, designed for)

Today `resolveConsentAnswer(category)` reads the fixed table above. The
natural extension later: check a per-user setting first (e.g.
`profile.consent_preferences?.[category]`), fall back to the table's
`default` only if the user hasn't set one. Because the policy layer is
already isolated in its own file/function, that extension touches ONLY
`extension/consent_policy.js` (and its Python mirror, if one is built) —
the interpreter, `category_mapping.py`, and `resolveValue()` never need to
change when it happens. A future `ASK_USER`/`FOLLOW_PROFILE_SETTING`
policy value is a change in one small file, not an interpreter change.
This is the concrete payoff of keeping policy separate from
classification.

## What replay.py measures (and doesn't) for these categories

`replay.py` scores classification accuracy only — "did we correctly
identify this field as `consent_sms_communication`." It has no visibility
into `resolveConsentAnswer()` at all (replay is Python-only, offline, and
never calls into `extension/consent_policy.js`). A coverage increase for
these 5 categories in a replay report means "we now correctly recognize
more consent questions," not "we're answering them well" — those are
different, deliberately separated claims. There is currently no automated
way to check whether `decline`/`accept` was the *right* call for any real
user; that would need real usage data (telemetry/`field_corrections`,
P2.3, not built yet) or product judgment, not corpus replay.
