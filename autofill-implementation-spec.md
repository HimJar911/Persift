# Building a Simplify-Style Job Application Autofill Engine — Implementation Spec

> A complete, opinionated reference for replicating the autofill mechanism used by tools like Simplify.jobs, built for a Chrome extension that fills job application forms across ATS platforms. This is a *general mechanism* reconstruction — not a copy of any company's source — assembled from how these systems demonstrably behave plus standard browser-extension engineering. Where a detail can only be learned by observing real forms, that is called out explicitly.

---

## 0. Mental model

An autofill engine is four loosely-coupled subsystems:

1. **Profile store** — structured user data rich enough to answer any field a form asks.
2. **Field detection & classification** — for every input on the page, decide *what it is asking for*.
3. **Value resolution & filling** — pick the right profile value, write it, and make the page's framework actually register the write.
4. **Coverage feedback loop** — detect misses in the wild and improve over time.

Most of the engineering difficulty is in #2 (detection) and the framework-eventing part of #3. The "moat" of a mature product is the ATS-specific adapters plus the telemetry that keeps them from rotting.

The single most important architectural decision: **adapter-first, generic-fallback.** Roughly 80%+ of real-world applications route through a handful of ATS platforms (Greenhouse, Lever, Workday, Ashby, iCIMS, Workable, SmartRecruiters, Taleo, Jobvite, BambooHR). Write dedicated logic for those; use a generic heuristic classifier for everything else.

---

## 1. Profile schema

If the data model is too thin, no amount of detection quality helps — you can't fill what you didn't store. Design the schema to be richer than you think you need, with arbitrary custom Q&A as an escape hatch.

```typescript
interface Profile {
  // Identity
  firstName: string;
  middleName?: string;
  lastName: string;
  preferredName?: string;
  pronouns?: string;

  // Contact
  email: string;
  phone: string;          // store E.164 + display variant
  phoneCountryCode?: string;

  // Location
  address: {
    line1?: string;
    line2?: string;
    city?: string;
    state?: string;       // store both full + 2-letter
    stateCode?: string;
    postalCode?: string;
    country?: string;     // store both full + ISO-2
    countryCode?: string;
  };

  // Links
  links: {
    linkedin?: string;
    github?: string;
    portfolio?: string;
    website?: string;
    twitter?: string;
    other?: { label: string; url: string }[];
  };

  // Work authorization (extremely common, legally specific)
  workAuth: {
    authorizedToWork?: boolean;          // "Are you authorized to work in the US?"
    requiresSponsorship?: boolean;       // "Will you now or in the future require sponsorship?"
    visaStatus?: string;                 // free text fallback
  };

  // Experience (array — forms often want most-recent or repeat sections)
  workExperience: Array<{
    company: string;
    title: string;
    location?: string;
    startDate?: string;   // ISO; you must reformat per form
    endDate?: string;     // or "Present"
    current?: boolean;
    description?: string;
  }>;

  education: Array<{
    school: string;
    degree?: string;       // "Bachelor's", "Master's", etc.
    fieldOfStudy?: string;
    gpa?: string;
    startDate?: string;
    endDate?: string;
    current?: boolean;
  }>;

  // Demographics / EEO (US): gender, race, veteran, disability
  // Store as canonical enum values; map to each form's option set at fill time.
  eeo?: {
    gender?: string;
    race?: string[];       // can be multi-select
    hispanicLatino?: boolean;
    veteranStatus?: string;
    disabilityStatus?: string;
  };

  // Job preferences
  preferences?: {
    desiredSalary?: string;
    salaryCurrency?: string;
    noticePeriod?: string;
    willingToRelocate?: boolean;
    workModelPreference?: string;   // remote/hybrid/onsite
    earliestStartDate?: string;
    howDidYouHear?: string;
  };

  // Documents
  documents?: {
    resumeFileRef?: string;   // see §7 on why you can't auto-set file inputs
    coverLetterFileRef?: string;
  };

  // The escape hatch: arbitrary saved answers keyed by a normalized question.
  // This is what lets you cover the long tail of custom screening questions.
  customAnswers?: Array<{
    questionKey: string;   // normalized/hashed question text
    questionText: string;  // original, for display
    answer: string;
    fieldType?: 'text' | 'select' | 'radio' | 'checkbox';
  }>;
}
```

**Key schema principles**

- **Store canonical + variants.** State as both `"California"` and `"CA"`; country as `"United States"` and `"US"`. Forms ask in both forms and you map at fill time rather than re-deriving.
- **Dates are a recurring nightmare.** Store ISO internally, reformat to whatever the form wants (`MM/YYYY`, `MM/DD/YYYY`, three separate dropdowns). Build one `formatDate(iso, pattern)` utility.
- **Booleans need value-set mapping.** "Authorized to work?" may render as Yes/No radios, a select with "Yes"/"No", or a checkbox. Store the boolean; resolve to the form's actual option labels at fill time.
- **`customAnswers` is the long-tail strategy.** Every unique screening question the user answers once gets saved, normalized, and reused. This is how coverage compounds over time.

---

## 2. Extension skeleton (Manifest V3)

```json
{
  "manifest_version": 3,
  "name": "Autofill Engine",
  "version": "0.1.0",
  "permissions": ["storage", "scripting", "activeTab"],
  "host_permissions": ["<all_urls>"],
  "background": { "service_worker": "background.js" },
  "content_scripts": [
    {
      "matches": [
        "*://boards.greenhouse.io/*",
        "*://job-boards.greenhouse.io/*",
        "*://*.lever.co/*",
        "*://*.myworkdayjobs.com/*",
        "*://*.ashbyhq.com/*",
        "*://*.icims.com/*",
        "*://*.workable.com/*",
        "*://*.smartrecruiters.com/*",
        "*://*.jobvite.com/*",
        "*://*.bamboohr.com/*"
      ],
      "js": ["content.js"],
      "run_at": "document_idle",
      "all_frames": true
    }
  ],
  "web_accessible_resources": [
    { "resources": ["injected.js"], "matches": ["<all_urls>"] }
  ]
}
```

Notes:

- **`all_frames: true`** matters — many ATS embed the application form in an iframe (Greenhouse is frequently embedded on a company's own careers domain via iframe). You need to run inside the frame that contains the form.
- For iframe-embedded forms on arbitrary company domains, `host_permissions: ["<all_urls>"]` plus dynamic injection via the `scripting` API from the background worker is more robust than a static match list. Many products use a broad match and detect the ATS at runtime by DOM signature rather than relying solely on URL.
- **`web_accessible_resources` / `injected.js`**: content scripts run in an *isolated world* and cannot see the page's framework internals directly. For the hardest cases (reading a React component's props, calling a page-level function) you inject a script into the page's main world. You usually don't need this for filling if you use the native-setter trick (§6), but keep the option open.

---

## 3. ATS detection at runtime

Don't trust the URL alone. Detect by DOM signature so you correctly handle embedded forms and white-labeled domains.

```javascript
function detectATS() {
  const url = location.href;
  const html = document.documentElement.outerHTML;

  // URL signals (fast path)
  if (/greenhouse\.io/.test(url)) return 'greenhouse';
  if (/lever\.co/.test(url)) return 'lever';
  if (/myworkdayjobs\.com/.test(url)) return 'workday';
  if (/ashbyhq\.com/.test(url)) return 'ashby';

  // DOM signature signals (for embedded/white-labeled forms)
  if (document.querySelector('#grnhse_app, [id^="greenhouse"]')) return 'greenhouse';
  if (document.querySelector('[data-qa="application-form"], .application-form .lever')) return 'lever';
  if (document.querySelector('[data-automation-id]')) return 'workday'; // Workday uses data-automation-id everywhere
  if (document.querySelector('._ashby_application_form, [class*="ashby"]')) return 'ashby';
  if (/icims/i.test(html)) return 'icims';

  return 'generic';
}
```

Maintain a small registry mapping each ATS id to its adapter module. The dispatcher loads the right adapter, falls back to `generic`.

---

## 4. Field detection & classification (the core)

This is where products win or lose. The naive "first regex match" approach breaks constantly. Build a **confidence-scoring** classifier.

### 4.1 Gather signals per field

For each `input`, `textarea`, `select`, and custom widget, collect every available signal:

```javascript
function getFieldSignals(el) {
  const labelText =
    (el.labels && el.labels[0]?.innerText) ||
    el.closest('label')?.innerText ||
    document.querySelector(`label[for="${el.id}"]`)?.innerText ||
    '';

  // Walk up for a question/section container (many ATS wrap each field in a div with the question text)
  const container = el.closest('[class*="field"], [class*="question"], fieldset, .form-group');
  const containerText = container ? container.innerText.slice(0, 200) : '';

  return {
    label: labelText.trim(),
    containerText: containerText.trim(),
    name: el.name || '',
    id: el.id || '',
    placeholder: el.placeholder || '',
    ariaLabel: el.getAttribute('aria-label') || '',
    ariaDescribedby: getReferencedText(el, 'aria-describedby'),
    autocomplete: el.getAttribute('autocomplete') || '',
    type: el.type || el.tagName.toLowerCase(),
    dataAttrs: getDataAttributes(el),     // Workday's data-automation-id is gold
    required: el.required || el.getAttribute('aria-required') === 'true',
  };
}
```

### 4.2 Signal confidence hierarchy

Not all signals are equal. Weight them:

| Signal | Confidence | Why |
|---|---|---|
| `autocomplete` attribute (`email`, `given-name`, `tel`) | Highest | Standardized, unambiguous when present |
| ATS-specific `data-*` (e.g. Workday `data-automation-id="email"`) | Highest | Stable, intentional |
| Associated `<label>` text | High | Human-facing, descriptive |
| `aria-label` / `aria-describedby` | High | Accessibility-intended description |
| Container/question text | Medium | Descriptive but noisy |
| `name` / `id` attribute | Medium-Low | Often abbreviated/machine-y |
| `placeholder` | Low | Sometimes an example value, not a label |

### 4.3 Scoring classifier

Instead of returning on first match, score every candidate field-type and pick the best above a threshold.

```javascript
const FIELD_DEFINITIONS = {
  firstName: {
    autocomplete: ['given-name'],
    patterns: [/first.?name/i, /given.?name/i, /\bfname\b/i, /legal first/i],
    negativePatterns: [/last/i, /maiden/i, /emergency/i, /reference/i, /supervisor/i],
  },
  lastName: {
    autocomplete: ['family-name'],
    patterns: [/last.?name/i, /surname/i, /family.?name/i, /\blname\b/i],
    negativePatterns: [/first/i, /maiden/i, /emergency/i, /reference/i],
  },
  email: {
    autocomplete: ['email'],
    patterns: [/e-?mail/i],
    negativePatterns: [/confirm/i, /reference/i, /supervisor/i, /manager/i, /emergency/i],
  },
  phone: {
    autocomplete: ['tel'],
    patterns: [/phone/i, /mobile/i, /\btel\b/i, /contact number/i],
    negativePatterns: [/emergency/i, /reference/i, /work phone/i, /fax/i],
  },
  linkedin: { patterns: [/linked.?in/i] },
  github: { patterns: [/git.?hub/i] },
  portfolio: { patterns: [/portfolio/i, /personal (web)?site/i] },
  // ... extend for every field type
};

const WEIGHTS = {
  autocomplete: 100,
  dataAutomationId: 100,
  label: 60,
  ariaLabel: 55,
  containerText: 35,
  name: 30,
  id: 25,
  placeholder: 15,
};

function classifyField(signals) {
  const scores = {};

  for (const [fieldType, def] of Object.entries(FIELD_DEFINITIONS)) {
    let score = 0;

    // Highest-confidence: autocomplete exact match
    if (def.autocomplete?.includes(signals.autocomplete)) {
      score += WEIGHTS.autocomplete;
    }

    // Pattern matching across weighted signals
    const weightedSignals = [
      ['label', signals.label],
      ['ariaLabel', signals.ariaLabel],
      ['containerText', signals.containerText],
      ['name', signals.name],
      ['id', signals.id],
      ['placeholder', signals.placeholder],
    ];

    for (const [signalName, text] of weightedSignals) {
      if (!text) continue;
      if (def.patterns?.some(p => p.test(text))) {
        score += WEIGHTS[signalName] || 10;
      }
      // Negative patterns subtract hard — this kills "emergency contact email" etc.
      if (def.negativePatterns?.some(p => p.test(text))) {
        score -= 80;
      }
    }

    if (score > 0) scores[fieldType] = score;
  }

  // Pick highest above threshold
  const ranked = Object.entries(scores).sort((a, b) => b[1] - a[1]);
  if (ranked.length && ranked[0][1] >= 40) {
    return { fieldType: ranked[0][0], confidence: ranked[0][1] };
  }
  return { fieldType: null, confidence: 0 };
}
```

### 4.4 The hard classification cases

These are what separate a toy from a real engine:

- **Negative matching.** "Emergency contact email", "Reference's phone", "Supervisor name", "Referrer email" all match naive patterns and are all *wrong*. Negative patterns + section-context awareness (is this field inside a `<fieldset>` labeled "References"?) are essential.
- **One-to-many decomposition.** A single "Full name" box must be filled with `firstName + ' ' + lastName`. "Full address" must be composed. Conversely, three date dropdowns (month/day/year) must be *decomposed* from one stored ISO date.
- **Many-to-one.** Don't fill both a "First name" and a "Full name" field with overlapping data on the same form. Track what's already been filled.
- **EEO / demographic value-matching.** Gender, race, veteran status, disability — these are `<select>` or radio sets with legally specific, employer-varying phrasing. You match your canonical value against the actual option labels with fuzzy matching ("Decline to self-identify" vs "I don't wish to answer" vs "Prefer not to say").
- **Work authorization logic.** "Will you now or in the future require sponsorship?" — note the polarity. A `requiresSponsorship: false` user answers "No" here, but "Yes" to "Are you legally authorized to work?". Get the polarity wrong and you've lied on someone's application. Encode the semantics, not just the keyword.
- **Custom screening questions.** "Why do you want to work here?", "Describe a time you…". Match against `customAnswers` by normalized question key; if no match, optionally generate via LLM (§9), and always save the user's eventual answer for reuse.

---

## 5. Filling native fields correctly

The number-one beginner mistake: setting `input.value = x`. React, Vue, Angular, and Svelte track input state internally; a direct property write doesn't trip their listeners, so the value visually appears but the framework's state stays empty — and on submit the form sends blanks or fails validation.

You must use the **native value setter** and dispatch the events the framework listens for:

```javascript
function setNativeValue(el, value) {
  const prototype = el instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype
    : HTMLInputElement.prototype;
  const nativeSetter = Object.getOwnPropertyDescriptor(prototype, 'value').set;
  nativeSetter.call(el, value);

  // Fire the events frameworks listen to. Order and coverage matter.
  el.dispatchEvent(new Event('input',  { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
}

function fillTextField(el, value) {
  el.focus();
  setNativeValue(el, value);
  el.dispatchEvent(new Event('blur', { bubbles: true })); // triggers validation on many forms
}
```

For **React specifically**, the native-setter trick is required because React overrides the `value` property descriptor on the element instance; calling the *prototype's* setter bypasses React's override and then the dispatched `input` event makes React pick up the "change."

Some forms additionally need keyboard events (`keydown`/`keyup`) to satisfy custom handlers. Add them only when a plain input+change doesn't register — they're slower and occasionally double-trigger.

---

## 6. Filling non-native widgets (the real work)

Native `<input>`/`<textarea>` are the easy 30%. The rest are custom React/Vue components that *look* like form controls but aren't.

### 6.1 Native `<select>`

```javascript
function fillSelect(selectEl, desiredValue) {
  const options = [...selectEl.options];
  // Match by value, then by visible text, then fuzzy
  const match =
    options.find(o => o.value === desiredValue) ||
    options.find(o => o.text.trim().toLowerCase() === desiredValue.toLowerCase()) ||
    options.find(o => o.text.toLowerCase().includes(desiredValue.toLowerCase()));
  if (!match) return false;
  selectEl.value = match.value;
  selectEl.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
}
```

### 6.2 Custom comboboxes (React-Select, Ashby, Workday dropdowns)

These are the hardest common case. There is no `<select>`. The flow is: click to open → wait for the listbox to render (often async) → find the matching option → click it.

```javascript
async function fillCombobox(triggerEl, desiredText) {
  triggerEl.click();                        // open the dropdown
  triggerEl.focus();

  // Some require typing to filter the option list
  const input = triggerEl.querySelector('input') || triggerEl;
  if (input.tagName === 'INPUT') {
    setNativeValue(input, desiredText);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  // Wait for options to render (async). Poll with a timeout.
  const option = await waitForElement(() => {
    const opts = document.querySelectorAll(
      '[role="option"], [class*="option"], li[id*="option"]'
    );
    return [...opts].find(o =>
      o.textContent.trim().toLowerCase().includes(desiredText.toLowerCase())
    );
  }, { timeout: 3000 });

  if (option) {
    option.click();
    return true;
  }
  return false;
}

function waitForElement(getter, { timeout = 3000, interval = 100 } = {}) {
  return new Promise((resolve) => {
    const start = Date.now();
    const tick = () => {
      const found = getter();
      if (found) return resolve(found);
      if (Date.now() - start > timeout) return resolve(null);
      setTimeout(tick, interval);
    };
    tick();
  });
}
```

### 6.3 Radio groups & checkboxes

Match the desired value against each option's label, then `.click()` the input (clicking, not setting `.checked`, so framework handlers fire).

```javascript
function fillRadioGroup(groupEls, desiredValue) {
  for (const radio of groupEls) {
    const label = radio.labels?.[0]?.innerText ||
                  radio.closest('label')?.innerText ||
                  document.querySelector(`label[for="${radio.id}"]`)?.innerText || '';
    if (fuzzyMatch(label, desiredValue)) {
      radio.click();
      return true;
    }
  }
  return false;
}
```

### 6.4 Shadow DOM

Some ATS hide inputs inside shadow roots; `document.querySelectorAll` won't reach them. Traverse recursively:

```javascript
function queryAllDeep(selector, root = document) {
  const results = [...root.querySelectorAll(selector)];
  const walk = (node) => {
    if (node.shadowRoot) {
      results.push(...node.shadowRoot.querySelectorAll(selector));
      node.shadowRoot.querySelectorAll('*').forEach(walk);
    }
  };
  root.querySelectorAll('*').forEach(walk);
  return results;
}
```

### 6.5 Cascading / dependent fields

Country → State → City, or Department → Sub-team. Selecting the parent triggers an async repopulation of the child. You must fill sequentially and *wait* for the child to populate before filling it. Never fire them in parallel.

---

## 7. File uploads (resume)

You **cannot** programmatically set a file `<input type="file">`'s `.files` for security reasons — the browser blocks it. There is no clean way around this for arbitrary forms. Real products handle it one of these ways:

- **Pre-fill everything else, leave the resume to the user.** Most honest and robust: fill the whole form, then surface a clear "drop your resume here" prompt.
- **Drag-and-drop simulation** works in *some* cases where the dropzone listens for `drop` events with a `DataTransfer` — you can construct a `DataTransfer`, add a `File` you built from stored bytes, and dispatch a synthetic `drop`. This is fragile and ATS-specific.
- **Native file picker** still requires a real user gesture to open and a real user selection; you can't fully bypass it.

Store the resume bytes (or a reference) in the extension so you can at least construct a `File` object for the drag-drop path where it works, and fall back to prompting otherwise.

---

## 8. Orchestration: multi-step forms, SPAs, and timing

Application forms are increasingly single-page apps with multi-step wizards. The page doesn't reload between steps; new fields appear dynamically.

### 8.1 MutationObserver re-fill (with guards)

```javascript
let fillInProgress = false;
const filledFields = new WeakSet();

const observer = new MutationObserver(debounce(async () => {
  if (fillInProgress) return;          // idempotency guard
  fillInProgress = true;
  try {
    await runAutofill();               // only fills fields not in filledFields
  } finally {
    fillInProgress = false;
  }
}, 400));

observer.observe(document.body, { childList: true, subtree: true });
```

Critical guards:

- **Idempotency.** Track already-filled fields (`WeakSet`) so re-runs don't overwrite a value the user just edited, and don't double-fire.
- **Debounce.** Frameworks mutate the DOM constantly; without debouncing you'll thrash and fight the framework's own re-renders.
- **Don't overwrite user edits.** Only fill empty fields, or fields you filled and the user hasn't touched since.
- **Respect validation races.** A field that validates on blur may show an error if you fill+blur before its async validator is ready. Where you see flakiness, add a small settle delay or re-check after validation completes.

### 8.2 Step detection

Detect "next page" transitions (URL change, step indicator change, new fieldset appearing) and re-run. Persist progress so a user who reloads mid-application doesn't lose filled state.

---

## 9. The long tail: LLM-assisted field mapping & answers

Two distinct uses, both optional but high-leverage:

1. **Unknown field mapping.** When the heuristic classifier returns null/low-confidence, send the field's signals (label, container text, attributes — *not* the user's PII) to an LLM and ask it to return the best matching profile key, or `null`. Cache the mapping per-domain so you pay once per form layout, not once per fill.

2. **Custom question answering.** For free-text screening questions with no saved answer, generate a draft from the user's profile + the job description, let the user edit, and save the final answer to `customAnswers` for reuse.

Cost/latency discipline: heuristics first, LLM only on misses, cache aggressively, and keep PII out of prompts where you can (send the *question*, get back a *mapping key*, fill locally).

---

## 10. Coverage feedback loop (the actual moat)

A static engine rots — ATS vendors push UI changes that silently break selectors. What keeps a mature product ahead is telemetry:

- **Log fill outcomes** per field per ATS per domain: detected? filled? did the user correct it afterward?
- **Detect failures in the wild**: fields that were present but unfilled, or filled-then-immediately-edited (a sign of a wrong mapping).
- **Surface a "fields we couldn't fill" count** so you have a coverage metric to drive down.
- **Prioritize adapter fixes** by volume — fix the ATS/field combos that fail most often.

This loop is presumably how these tools reached their coverage: ship the skeleton, instrument everything, iterate against real applications. There is no shortcut that replaces seeing thousands of real forms.

---

## 11. Per-ATS adapter notes

Each adapter is a module exposing `detect()`, `getFields()`, and optional custom fillers. Quirks worth knowing:

- **Greenhouse** — relatively clean, mostly native inputs with stable `id`/`name` (`first_name`, `last_name`, `email`, `phone`). Often embedded via iframe on company domains (`grnhse_app`). Custom questions have predictable `question_*` ids. One of the easiest, highest-value adapters to write first.
- **Lever** — clean `name` attributes (`name`, `email`, `phone`, `org`, `urls[LinkedIn]`). Cards/sections are predictable. URL fields are an array-style name.
- **Workday** — the hostile one. Everything keyed off `data-automation-id` (which is, ironically, your best high-confidence signal once you learn the values). Heavy custom widgets, shadow-ish nesting, slow async rendering, multi-step wizard, cascading location dropdowns. Budget the most time here. `data-automation-id="email"`, `"legalNameSection_firstName"`, etc.
- **Ashby** — modern React, React-Select-style comboboxes, async option rendering. Needs the combobox flow in §6.2. Class names are hashed/obfuscated, so lean on `role` and label text, not classes.
- **iCIMS** — older, often iframe-embedded, sometimes table-based layouts. Detect by content, fall back to generic heuristics more often.
- **Workable / SmartRecruiters / Jobvite / BambooHR** — each has its own field-naming conventions; write thin adapters as volume justifies, generic handles them passably in the meantime.

Write adapters in priority order of *your users' actual traffic*. Don't build Taleo support before you've seen a single Taleo application.

---

## 12. Security, privacy, and trust posture

You're reading/storing PII and injecting on every job site — this is a trust product. Decisions that matter:

- **Local-first storage.** `chrome.storage.local` keeps PII on-device. If you sync or send anything to a server (for LLM mapping, telemetry), be explicit and minimize.
- **Minimize PII in any network call.** For LLM field mapping, send field *descriptors*, not the user's data.
- **Scope injection.** Broad `host_permissions` is powerful and scary; document why you need it and consider activeTab + dynamic injection to reduce always-on surface.
- **Never auto-submit.** Fill, then let the human review and submit. Auto-submitting applications is both an ethics and a liability problem (you could submit wrong/false answers, e.g. work-auth polarity bugs).
- **Be careful with EEO/demographic data.** It's sensitive; let users leave it blank by default and opt in.

---

## 13. Build order (pragmatic sequence)

1. Profile schema + a settings UI to populate it.
2. Native-setter fill utility (`setNativeValue`) — get React eventing right *first*; nothing works without it.
3. Greenhouse adapter end-to-end (easiest, high value). Prove the full loop on one ATS.
4. Generic scoring classifier as fallback.
5. Lever + Ashby adapters (Ashby forces you to solve comboboxes).
6. MutationObserver orchestration for multi-step/SPA.
7. Workday adapter (hardest; do it when traffic justifies the time sink).
8. Telemetry / coverage loop.
9. LLM mapping + custom-answer generation for the long tail.
10. Resume drag-drop where feasible, prompt fallback everywhere else.

---

## 14. What this document can't give you

This is the *general mechanism*, reconstructed from observable behavior and standard extension engineering — not any company's literal source. I don't have their exact heuristic weights, their full adapter list, their option-matching dictionaries, or their failure-telemetry internals. Those were learned by running against thousands of real forms. Anyone claiming a byte-exact spec of a competitor's internals from the outside is guessing.

The honest path to "best efficiency" is the one these tools presumably took: build the skeleton above, instrument every fill, and grind the coverage up against real applications — adapter by adapter, field by field, miss by miss.
