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

Section-3 fill mechanisms survive unchanged (native-setter text fill, native select, React combobox via aria-controls, typeahead, radio/checkbox groups, intl-tel-input, file upload). New: after each fill, **re-check the DOM** (`isInputFilled` on the element / group) because React re-renders silently revert writes; on failure, one alternate strategy (e.g. combobox click-select → keyboard navigation), then record `verified: false` and move on. Built in P1.5 (Aug 2 2026): `extension/filler_utils.js`'s `runPass`/`retryFill`.

**Known limitation, not yet fixed — see [decisions/0010](decisions/0010-verification-is-mechanical-not-semantic.md):** `isInputFilled()` verification is mechanical, not semantic. It confirms a value landed in the field, not that it's the *correct* value for what the field is asking — a misclassified field with a resolvable profile value logs identically to a correctly-classified one. Read `verified: true` as necessary, not sufficient, evidence of correctness.

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

#### 3.6a Corpus harvester — detailed design (locked Jul 17, 2026)

**Origin of this design:** P1.1 (rich extraction) shipped Jul 17 with `section` verified live against exactly one posting (ACLU/Greenhouse) — a debug session started hand-tuning `getFieldSection()` against individual forms to fix bad output, which is precisely the form-by-form-optimization anti-pattern standing rule §1 forbids. Caught mid-session; the fix was to stop hand-tuning and defer real validation to the corpus/replay system instead of continuing to eyeball single forms. This section is the design for that system, converged Claude ↔ ChatGPT ↔ founder (same discussion-first process as the original engine design).

**Founding principle:** the harvester must NOT reuse `enrichField()`/`collectFields()` as-is. That code encodes assumptions we already made by staring at 2-3 forms (label-first discovery, a specific `section` heuristic, etc.) — running it to build the corpus would just collect more instances of the same blind spots, not reveal new ones. The harvester needs a wider, independent capture pass; P1.4's interpreter gets *designed from* what the corpus reveals, not the other way around. "Here's 1000 real forms, deeply analyzed, THEN build the autofill around that" — not "extend the autofill we already guessed at."

**Field discovery — exhaustive, not label-first.** Enumerate every `input`, `select`, `textarea`, and `[role="combobox"|"radio"|"checkbox"]` on the page directly, independent of whether a label can be found. Today's `collectFields()` is label-first and structurally cannot discover "a category of fields with no detectable label" — it never sees them in the first place. For each element: attempt label detection via the existing 5-strategy `getLabelForEl` logic (reuse fine here — it's a best-effort *attempt*, not a filter), and record `labelFound: false` explicitly, plus which of the 5 strategies matched when one did (label-strategy provenance).

**Identity vs. semantics split (converged with ChatGPT, Jul 17):**
- `field_id_hash` — stable dedup/replay identity, hashed from only the structurally stable DOM attributes: `tag + htmlType + name + id + autocomplete + role`. Deliberately excludes anything interpretive.
- `field_semantics` — everything contextual/interpretive, stored but never used for identity: `label` (+ which strategy found it), `section`, `ancestorClasses` (full chain, array), `nearbyText`, `options`, `description`, plus everything `enrichField()` already captures (placeholder, ariaLabel, ariaLabelledByText, inputMode, pattern, maxLength, containerHTML).
  - Why the split: `section`/`ancestorClasses`/label text are exactly the shaky, single-form-verified heuristics from P1.1. If they were hash inputs, "the same field becomes a different field" the moment page structure shifts slightly — the hash must be identity, not evidence.

**Per-field state (new, not in P1.1's `enrichField`):** `visible` (`offsetParent !== null`), `disabled`, `readOnly`, `hidden` (self or any ancestor `display:none`/`[hidden]`/`aria-hidden`/collapsed-looking). Matters for replay — a field's reachability (e.g. "only appears after selecting X elsewhere") is itself a signal.

**Radio/checkbox — two-layer record.** One group-level record (label, section, etc. — group semantics) plus per-option sub-records (each option's own label/value text). Not collapsed into a single `options: string[]` the way `enrichField()` does today — a lot of Greenhouse questions are group-level semantic objects where each option's own text matters for later interpretation.

**Page-level record:**
- `job_id`, `ats`, `company_name`, `url`, `crawl_started_at`, `crawl_finished_at`
- `apply_click_needed: boolean` — some Greenhouse postings gate the real form behind an "Apply" click (§0); recording this separates "0 fields because no form exists" from "0 fields because we didn't know to click Apply"
- `extraction_status`: `ok | partial | no_form_found | apply_button_clicked_no_form | shadow_dom_unhandled | iframe_unhandled | error` — without this, a failed/partial crawl looks identical to "a form with genuinely 0 interesting fields," silently corrupting P1.3's coverage %.
- `page_html_path` — pointer to a sidecar file (see storage below), not inlined
- Array of field records (each with `field_id_hash` + `field_semantics` + state)

**Snapshot timing:** post-render, post-Apply-click (if needed), pre-fill. Never touches values (same A/B-only PII discipline as `field_corrections`, migration 015 — standing rule §1.4).

**Storage:** JSONL manifest (one line per page — metadata + field array), NOT inlining full page HTML (would make the manifest unwieldy to load/grep/replay at 500+ forms). Full-page HTML/DOM snapshot saved as a separate gzipped sidecar file per page (named by page hash or `job_id`), referenced from the manifest by path. The full-page snapshot is a safety net — if P1.3 later reveals a signal we didn't think to extract per-field, it can be mined from the saved page without re-crawling (the live posting may be gone/changed by then).

**Crawl mechanics:** Playwright headless Chromium (forms are React-rendered, sometimes behind an Apply click — a real browser engine is required, not an HTTP fetch). Source: `jobs` table `WHERE ats='greenhouse'` (Greenhouse first, matches P1.6–P1.8 adapter build order). Rate-limited + jittered delay between requests, daily cap. Read-only throughout — no profile, no API, no claim, no submission. Target 500+ forms before P1.4 gets written.

#### 3.6b Corpus open-coding — category taxonomy built from the corpus (done Jul 20, 2026; extended to full Greenhouse volume Jul 29, 2026)

**All 3,074 fields across 116 usable-form companies from the P1.2 corpus have been individually classified.** Full pipeline, decision files, and reasoning trail live in `corpus_analysis/` (tracked in git — read `corpus_analysis/README.md` first, it is the authoritative account of this pass, this section is a summary only). This is the direct predecessor to P1.3/P1.4: it produces the category taxonomy and a hand-verified answer key that the replay harness scores against, and that the interpreter's rules get designed from.

**UPDATE Jul 29, 2026 — extended to the full Greenhouse harvest.** The 116-company pass above was extended to cover ALL 17,391-17,396 companies / ~633K fields from P1.2's full-volume re-run (`corpus/README.md` "Two harvest runs"), not left as a small-sample answer key. Result: 99.2% overall field coverage, 97 confirmed categories (`corpus_analysis/taxonomy_v1.py`). Critically, this pass added a **held-out company-level generalization test** the original 116-company pass never had: running the finished taxonomy cold against 20 companies never seen during taxonomy-building scored **99.0% coverage / 100% correctness (60-field sample)** — evidence the taxonomy generalizes to unseen forms, not just the companies it was read from. Use `corpus_analysis/oc_compact_full_v2.json` + `cluster_decisions_v2.json` (not the original `oc_compact_full.json`/`cluster_decisions.json`) as the answer key for P1.3 going forward. Full detail: `corpus_analysis/README.md`'s "Full-volume extension" section, `STATE.md`'s RESUME HERE.

**Method, in order of trust:** (1) deterministic clustering — exact/near-exact matches on `id`, `autocomplete`, normalized label, section-as-fallback-label, and one known bad-pattern signature; zero semantic guessing. (2) Founder + agent read every remaining field individually, in small batches, confirming each one in conversation before it was written to a file; raw saved HTML (`corpus/pages/{job_id}.html.gz`) pulled and checked whenever a label was ambiguous or a cross-company pattern's real nature was in doubt. (3) A narrow, evidence-bounded auto-match (≥0.60 word-overlap against an already-founder-confirmed category's example labels) for the small remainder, spot-checked for false positives before trusting. `needs_review` — the pile requiring real judgment — is now 0.

**Result:** 110+ categories, effectively all traceable to one or more real fields a human actually read (not pattern-invented). Two systemic extraction bugs found and documented in `corpus_analysis/README.md` (a malformed empty-record harvester artifact; a placeholder-text-carries-the-real-question gap that `label` extraction misses). One real self-correction mid-pass: an early cluster merge (`department_interest`/`location_preference`, built from cross-company checkbox-group label matches) turned out to be ~95% wrong — job-board filter widgets and a cookie-consent banner masquerading as real application fields, caught only because one instance got checked against raw HTML out of caution rather than trusted on pattern alone. See `corpus_analysis/README.md`'s "department_interest / location_preference correction" section — the lesson there (cross-company checkbox-group text matches need raw-HTML verification before trust, even when they look obviously real) should carry into P1.4's own validation discipline, not just this one-time cleanup.

**Not done yet, explicitly upstream P1.4 work:** the category list is not yet formalized into a single canonical enum — it currently only exists as the union of values scattered across `corpus_analysis/`'s decision JSON files. Some category names are working names, not finalized (e.g. `pep_disclosure`, `attention_check`). Structural categories that aren't simple facts (`other_followup`, the honeypot pattern, the react-select shim) need their own resolution-layer handling, not just a label — see §7 below and `corpus_analysis/README.md`'s "category system" section for the full list.

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

LAUNCH_PLAN.md Phase 1 (Jul 8–15, dates now stale — see STATE.md for real progress): P1.1 rich extraction → P1.2 corpus harvester → **corpus open-coding (§3.6b, DONE Jul 20, extended to full volume Jul 29)** → **P1.3 replay harness (DONE Aug 2)** → **P1.4 multi-signal interpreter (DONE Aug 2)** → **P1.5 verify/retry + live wiring (DONE Aug 2)** → P1.6–P1.8 adapters (NEXT). Telemetry endpoint = P2.3 (rides auth). LLM fallback = post-pitch, post-corpus.

## 6. Open questions (decide during Phase 1, not silently)

- UNKNOWN threshold for the Phase 1 exit check (pick once the first corpus report exists).
- Telemetry storage: new table vs. extending `field_corrections` — decide with the P2.3 schema pass.
- Where serialized corpus lives during Phase 1 (local JSONL is fine pre-telemetry-API).
- Essay handling until LLM fallback exists: leave blank + telemetry (current lean) vs. always route to `awaiting_review`.

## 7. Resolution-layer rules decided during corpus open-coding (Jul 20, 2026)

Decided while manually open-coding P1.2's corpus (767 forms, 116 usable) into categories ahead of P1.4. Not yet implemented — these are resolution-layer behavior rules to carry into P1.4/P1.5, recorded here so they aren't lost or re-litigated silently.

- **Required field with no resolvable profile value → abort the application, don't guess or submit incomplete.** Concrete case: "Personal or Professional Website (Optional)" — if the user's profile has a portfolio/website URL, fill it (`personal_website` category). If empty and the field is marked optional, leave blank and proceed. If empty and the field is `required`, the interpreter must NOT fill garbage or leave it empty and submit anyway — the correct behavior is to skip the whole job (do not submit), the same failure-safe posture as an unresolvable required field generally. This is a general rule, not specific to website fields — any required field the resolver can't confidently answer should trip the same abort path.
- **React-Select's hidden `required`-shim input is not a real field, not "phone," not askable — and it trails EVERY custom combobox on the page, not just phone/country.** Initially found on the phone/country widget (49 corpus instances); broadened after finding a single 617mediagroup page (job 6917269002) with SIX shim occurrences — one per custom combobox on that page (country/phone, location, discipline, school, degree). 75 total corpus instances across 53 companies once broadened — same shared Greenhouse form-builder template, not coincidence. Signature: `tabindex="-1" aria-hidden="true" required` `<input>` with a `remix-css-*-requiredInput`-style class, injected immediately after any custom combobox. Confirmed via raw saved HTML, not guessed from label text. Purpose: lets a non-native combobox participate in native HTML5 `required` form validation. Extraction should learn to recognize and flag this pattern (hidden + `tabindex="-1"` + a value-less shim immediately trailing any real combobox, not just phone) so it's excluded from both the field corpus's "real question" count and from anything the interpreter tries to classify/fill — it resolves itself once the combobox it shims is filled correctly.
- **"Other, please specify" follow-up fields are a structural relationship, not a topic category.** Very common pattern (found repeatedly across the corpus): a free-text field whose only content is "If you selected Other above, please specify" / "If yes, please explain" — the field's own label carries zero information about what it's really asking; that only exists in the *preceding* field's answer. Modeled during open-coding as category `other_followup`, but a real category name is the wrong shape for this — the interpreter needs to detect the pattern (generic follow-up phrasing) and resolve it by looking at the nearest preceding field's selected value, not by classifying the follow-up field's own label text. Don't build `other_followup` as just another entry in the category enum; it needs its own resolution mechanism.
- **Extraction gap: some real questions live in `placeholder`, not `label`.** Confirmed on independent examples across multiple companies/platforms (Anduril/Gem ATS, Workato, Trade Republic) during open-coding — `label` extracts empty but `placeholder` carries the actual question (e.g. Trade Republic: `label: ""`, `placeholder: "Are you available and in Berlin between 15 July and 15 Oct 2026?"`). Not a one-off; `enrichField()`/`collectFields()` (or the P1.4 successor) should fall back to `placeholder` when `label` is empty, same spirit as the already-known `section`-as-fallback-label pattern used in the corpus analysis tooling (not yet ported into the live extension).
