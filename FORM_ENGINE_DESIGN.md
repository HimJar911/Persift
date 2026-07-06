# Persift Form Engine — Design (LOCKED)

*Locked July 5, 2026, discussion-first (Claude ↔ ChatGPT ↔ founder convergence). This is the authoritative design for the autofill engine. Build order and dates live in `LAUNCH_PLAN.md` Phase 1; this doc is the what-and-why.*

> **For future sessions:** read this before touching `extension/filler_utils.js`, any `extension/content/*.js` adapter, field classification, or telemetry. The standing rules in §1 override ad-hoc instincts — especially rule 1.

---

## 0. Problem statement

The previous workflow was per-application patching: a Greenhouse form fails → add a regex/synonym → next form surfaces a new exception. That is test-driven development with a sample size of one. The classifier's only input was a single label string, so fields with weak/absent labels (no-label GitHub inputs, consent checkboxes, misclassified comboboxes, essay questions — all seen live on the Gemini Greenhouse form) were invisible or wrong, and every fix generalized poorly.

The existing architecture was NOT the problem — `filler_utils.js` already separates a generic engine from thin ATS adapters. The problem was (a) classification from one signal, (b) no feedback loop, (c) no way to measure whether a change generalized. Scope decision: Persift will eventually autofill **arbitrary company career pages**, not just known ATSes — which weights everything below toward the generic engine over per-ATS logic.

## 1. Standing rules (non-negotiable)

1. **Never optimize to "make this application pass."** The goal of any fix is to improve the generic parser without introducing ATS-specific logic, unless the issue is genuinely caused by an ATS implementation detail (which belongs in that ATS's adapter).
2. **Extraction is sacred.** Extraction is the ONLY layer that reads the DOM *to understand the form*. After it emits `Field[]`, no other layer re-derives meaning from the DOM. Fill/Verify touch the DOM **mechanically only**, through the element handle a Field carries — never `field.el.closest(...)` to find a missing label. If a signal is missing, the fix goes in extraction. Every time.
3. **Interpretation is a pure function** over the serialized Field (no DOM, no globals, no network). This is what makes the replay harness trustworthy: interpretation/resolution are replayable offline; fill/verify are not, and replay only ever measures the pure layers.
4. **Telemetry captures field metadata, never filled values.** Same A/B-only PII discipline as `field_corrections` (migration 015). Container HTML is captured pre-fill with `value` attributes stripped.
5. **The KPI is per-category field coverage over the corpus** ("did UNKNOWN go down without hurting other categories"), not whether company X's form passed. Named forms (Gemini, OfferUp, …) are test cases in the corpus, nothing more.
6. **Consent/background-check checkboxes are auto-checked on the user's behalf** (founder decision, Jul 2026): core to auto-apply, not a risk to hedge on.

## 2. Pipeline

```
Browser DOM
    │
    ▼
━━━ EXTRACTION ━━━━━━━━━━  reads DOM exactly once → Field[]
    │
    ▼
━━━ INTERPRETATION ━━━━━━  pure fn: Field → canonical category + confidence
    │                       (FIRST_NAME, WORK_AUTH, CONSENT, ESSAY, UNKNOWN, …)
    ▼
━━━ RESOLUTION ━━━━━━━━━━  category + profile + context → answer + synonyms
    │                       (today's resolveValue, largely unchanged)
    ▼
━━━ FILL → VERIFY → RETRY  write via element handle; re-check DOM state;
    │                       one alternate strategy on failure
    ▼
━━━ TELEMETRY ━━━━━━━━━━━  serialized Field + classified_as + filled + verified
    │                       (+ corrected, via field_corrections diff) → API
    ▼
━━━ REPLAY ━━━━━━━━━━━━━━  offline: re-run interpreter over stored Fields →
                            coverage report per category
━━━ LLM FALLBACK ━━━━━━━━  LAST, gated: low confidence / ESSAY / unknown.
                            Deferred until the corpus shows the actual tail.
```

“Interpretation” (not “classification”) because the layer goes beyond labeling: consent → default action *check*; compensation → *parse the JD range on the page (extraction captures it) and answer midpoint*. It interprets intent, not just identity.

## 3. Layer specs

### 3.1 Extraction → the Field object

Evolves `collectFields()` (its 7 discovery strategies and radio/checkbox grouping are kept). Output per field:

```js
Field {
  element,            // live handle — carried for fill/verify ONLY, stripped on serialization
  label,              // via getLabelForEl's 5 strategies (kept)
  placeholder,
  name,               // e.g. "candidate[first_name]" — high-signal
  id,
  autocomplete,       // e.g. "given-name" — highest-signal when present (HTML spec semantics)
  ariaLabel, ariaLabelledByText, role,
  inputType,          // text | textarea | native_select | combobox | radio | checkbox | file
  htmlType,           // raw type attr; also inputmode/pattern/maxlength when present
  required,
  options,            // visible option/radio/checkbox texts (for selects/groups)
  section,            // nearest section heading (e.g. "Personal Information", EEO block)
  description,        // help text tied to the field
  nearbyText,         // surrounding paragraph text (consent language lives here)
  containerHTML,      // sanitized: captured PRE-fill, value attributes stripped
}
```

Serialization = everything minus `element`. That serialized form is the telemetry record, the corpus record, and the replay input — one representation for all consumers.

### 3.2 Interpretation

Pure: `interpret(field) → { category, confidence, action? }`.

Signal priority (HTML-semantics priors — legitimate on day one, refined by telemetry later, and telemetry also prunes dead rules):

```
autocomplete  >  name / id  >  label  >  placeholder  >  nearbyText / section
```

The current `FIELD_PATTERNS` regexes (~45 categories, positive + negative guards) are **demoted to the label-tier signal source inside the interpreter** — they stop being the whole engine and stop being a public name. Categories keep the `category__inputType` duality (same question answers differently as radio vs textarea).

New canonical categories: `consent_background_check` / `consent_privacy_policy` / `consent_generic` (action: check), `export_control`, `essay` (action: route to LLM fallback when built; until then, leave blank + telemetry), `UNKNOWN` (telemetry). Confidence starts coarse (which tier matched, how many tiers agree); numeric calibration comes only after telemetry provides ground truth (§3.6).

### 3.3 Resolution

`resolveValue(category, profile, context)` survives largely as-is (its category-key ↔ `getProfile()` JSON ↔ `application_settings` naming contract is unchanged — see ARCHITECTURE.md). Compensation's JD-range scan moves its *reading* into extraction (page salary range becomes Field/page context), keeping resolution DOM-free.

### 3.4 Fill → Verify → Retry

Section-3 fill mechanisms survive unchanged (native-setter text fill, native select, React combobox via aria-controls, typeahead, radio/checkbox groups, intl-tel-input, file upload). New: after each fill, **re-check the DOM** (`isInputFilled` on the element / group) because React re-renders silently revert writes; on failure, one alternate strategy (e.g. combobox click-select → keyboard navigation), then record `verified: false` and move on.

### 3.5 Telemetry

Every processed field emits (batched to the API, e.g. with `/submitted` or `/released`):

```json
{ "ats": "...", "url": "...", "field": { …serialized Field… },
  "classified_as": "...", "confidence": 0.0, "filled": true, "verified": true }
```

Skips (`UNKNOWN`), fills, and verify-failures all emit. `field_corrections` (two-snapshot diff, migration 015 — capture still unbuilt) is the fourth stream: *corrections tell us where interpretation was wrong; skips tell us where it was absent; verified fills tell us where it worked.* Design the capture together. **Note:** the API has no auth yet (LAUNCH_PLAN P2.1); the telemetry endpoint lands with the auth work, not before.

### 3.6 Replay harness + corpus

- **Corpus harvester (offline, day one):** Playwright, read-only, over our own `jobs` table's Greenhouse (then other-ATS) posting URLs — forms are React-rendered and sometimes behind an Apply click, so it's a headless browser, not an HTTP crawl. Polite rate (slow, jittered, daily cap). Needs no profile/API/claim. Target 500+ forms serialized before writing new interpretation rules. (Depends on LAUNCH_PLAN P0.2 — ingestion fix — for trustworthy URLs.)
- **Replay:** CLI loads stored serialized Fields, runs the interpreter, reports per-category coverage %. Every parser change answers one question: *did UNKNOWN go down without hurting the others?*
- **Later — confidence calibration:** verification + corrections provide ground truth ("said 0.95 — was it right?"). Once calibrated, confidence gates routing: high → auto-fill, mid → LLM, low → leave blank. A query over telemetry, not a new subsystem.

### 3.7 ATS adapters

Adapters (`content/greenhouse.js`, `ashby.js`, upcoming `lever.js`, `smartrecruiters.js`) own **lifecycle only**: handshake, form detection, resume-upload-first (uploads reveal fields), submit flow, success detection, review handoff. Zero interpretation logic. Ashby migrates onto the engine; Lever/SR are built on it from the start (LAUNCH_PLAN P1.6–P1.8).

## 4. Relationship to existing code

| Today (`filler_utils.js`) | Becomes |
|---|---|
| §1 `FIELD_PATTERNS`, `QUESTION_ALIASES`, visa/EEO maps | Label-tier signals + resolution data inside the interpreter |
| §2 `collectFields`, `getLabelForEl`, `getLabelForGroup` | Extraction layer (extended to emit rich Fields) |
| §3 fill mechanisms | Fill layer, unchanged + verify/retry wrapper |
| §4 `resolveValue`, `findCustomAnswer` | Resolution layer, near-unchanged |
| §5 `runFillerLoop` / `runPass` | Orchestrator over the new pipeline (multi-pass + DOM-stability wait kept) |

`autofill-implementation-spec.md` (generic Simplify-style reference) is superseded by this doc as the decision record; keep as implementation reference through Phase 1, then archive/delete.

## 5. Build order

LAUNCH_PLAN.md Phase 1 (Jul 8–15): P1.1 rich extraction → P1.2 corpus harvester → P1.3 replay harness → P1.4 multi-signal interpreter → P1.5 verify/retry → P1.6–P1.8 adapters. Telemetry endpoint = P2.3 (rides auth). LLM fallback = post-pitch, post-corpus.

## 6. Open questions (decide during Phase 1, not silently)

- UNKNOWN threshold for the Phase 1 exit check (pick once the first corpus report exists).
- Telemetry storage: new table vs. extending `field_corrections` — decide with the P2.3 schema pass.
- Where serialized corpus lives during Phase 1 (local JSONL is fine pre-telemetry-API).
- Essay handling until LLM fallback exists: leave blank + telemetry (current lean) vs. always route to `awaiting_review`.
