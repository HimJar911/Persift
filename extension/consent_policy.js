// Consent-question policy layer — deliberately SEPARATE from
// classification (extension/filler_utils.js's FIELD_PATTERNS/
// classifyField) and from resolveValue() (profile-fact lookups only).
//
// Why this file exists instead of living inside resolveValue(): an
// earlier version of this feature put accept/decline logic directly
// inside detect_structural_pattern()/detectStructuralPattern() (the
// interpreter). That was rejected — the interpreter answers "what is this
// field asking," a semantic question the corpus can validate; consent
// defaults answer "what should we do about it," a product/policy decision
// the corpus has no signal for. A second draft put the answer directly in
// resolveValue()'s switch, which was also rejected — resolveValue() means
// "given a category, retrieve the PROFILE value," and consent answers
// aren't profile facts, they're policy defaults. Keeping this logic in its
// own file/function means:
//   - resolveValue() stays exactly what its name says.
//   - replay.py continues to measure ONLY semantic classification
//     accuracy (did we correctly identify consent_sms_communication),
//     never "was declining the right call" — a question the corpus can't
//     answer at all.
//   - A future per-user override (see CONSENT_DEFAULT_IMPLEMENTATION's
//     `overridable` field below) is a change to ONLY this file — the
//     interpreter, category_mapping.py, and resolveValue() never need to
//     change when that happens.
//
// `requiredByEmployer` and `overridable` are independent fields, not one
// derived from the other. An earlier version set overridable:false for
// "required" categories on the assumption that required consent isn't a
// real user choice — that's wrong: a user can always decline a background
// check, the consequence is simply that the application can't proceed.
// Whether the employer requires the consent and whether the user is
// allowed to override the default are separate facts about a category.
// overridable has no runtime effect today (no settings UI reads it yet) —
// it exists so a future override implementation has a real flag to check
// instead of re-deriving one from `requiredByEmployer`.
'use strict';

const CONSENT_DEFAULT_IMPLEMENTATION = {
  consent_background_check: {
    default: 'accept',
    rationale: 'Declining blocks the application from proceeding, so the default is accept — but the user could still choose to decline and abandon this application, which is a real choice, not an impossible one.',
    requiredByEmployer: true,
    overridable: true,
  },
  consent_privacy_policy: {
    default: 'accept',
    rationale: 'Required acknowledgment to proceed, same shape as ToS.',
    requiredByEmployer: true,
    overridable: true,
  },
  consent_gdpr_notice: {
    default: 'accept',
    rationale: 'Required data-processing acknowledgment.',
    requiredByEmployer: true,
    overridable: true,
  },
  consent_sms_communication: {
    default: 'decline',
    rationale: 'Optional communication-channel opt-in, not required to apply — user has not opted in, so do not opt them in on their behalf.',
    requiredByEmployer: false,
    overridable: true,
  },
  marketing_communications_optin: {
    default: 'decline',
    rationale: 'Explicitly promotional/marketing opt-in — clearly voluntary.',
    requiredByEmployer: false,
    overridable: true,
  },
  consent_demographic_survey: {
    default: 'decline',
    rationale: 'Explicitly voluntary participation in a demographic/diversity survey, not required to apply — user has not opted in, so do not opt them in on their behalf.',
    requiredByEmployer: false,
    overridable: true,
  },
};

// Candidate value+synonym lists for fuzzy-matching against a real form's
// actual option text — same approach every other combobox/checkbox fill
// in this file already uses (see fillReactCombobox/fillCheckboxGroup).
const ACCEPT_CANDIDATES = ['Yes', 'I agree', 'I consent', 'Accept', 'I understand and agree'];
const DECLINE_CANDIDATES = ['No', 'I do not consent', 'Decline', "I don't wish to", 'Prefer not to'];

// True for any category this policy layer answers — the dispatcher in
// fillField() checks this before deciding whether to call
// resolveConsentAnswer() or resolveValue().
function isConsentCategory(category) {
  return Object.prototype.hasOwnProperty.call(CONSENT_DEFAULT_IMPLEMENTATION, category);
}

// Returns { value, synonyms } for a consent category, or null if the
// category isn't consent-policy-backed. Does NOT touch profile/context —
// deliberately: the answer here doesn't depend on user data, only on the
// category itself (today) or, in a future per-user-override extension, a
// per-user consent preference (not built yet — see module docstring).
function resolveConsentAnswer(category) {
  const entry = CONSENT_DEFAULT_IMPLEMENTATION[category];
  if (!entry) return null;
  const candidates = entry.default === 'accept' ? ACCEPT_CANDIDATES : DECLINE_CANDIDATES;
  return { value: candidates[0], synonyms: candidates.slice(1) };
}
