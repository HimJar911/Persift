// filler_utils.js — shared form-filling utilities for all ATS content scripts.
// Injected before each ATS content script via manifest.json content_scripts.
// All functions are globals — no ES module syntax (Chrome content script limitation).

'use strict';

// ── Section 1: Data Maps ──────────────────────────────────────────────────────

const VISA_ALIASES = {
  'F1':             ['F1', 'F-1', 'F1/CPT', 'F-1/CPT', 'F1 (CPT)', 'F-1 (CPT)',
                     'Student Visa', 'Student (F-1)', 'F1 Student', 'F-1 Student',
                     'F1/OPT', 'F-1/OPT', 'F1 Visa', 'F-1 Visa'],
  'F1_OPT':         ['OPT', 'F1 OPT', 'F-1 OPT', 'Optional Practical Training',
                     'Post-graduation OPT', 'F-1 (OPT)', 'F1 (OPT)'],
  'F1_STEM_OPT':    ['STEM OPT', 'F1 STEM OPT', 'F-1 STEM OPT', 'STEM Extension',
                     'OPT STEM', 'STEM OPT Extension'],
  'J1':             ['J1', 'J-1', 'J1 Visa', 'J-1 Visa', 'Exchange Visitor',
                     'J-1 (Academic Training)', 'J1 (Academic Training)'],
  'H1B':            ['H1B', 'H-1B', 'H1-B', 'H1B Visa', 'H-1B Visa', 'H1B Sponsored'],
  'H4_EAD':         ['H4 EAD', 'H-4 EAD', 'H4', 'H-4', 'EAD (H4)', 'H-4 (EAD)'],
  'L1':             ['L1', 'L-1', 'L1 Visa', 'L-1 Visa', 'Intracompany Transfer'],
  'O1':             ['O1', 'O-1', 'O1 Visa', 'O-1 Visa', 'Extraordinary Ability'],
  'TN':             ['TN', 'TN Visa', 'TN Status', 'Trade NAFTA', 'TN (NAFTA/USMCA)'],
  'E3':             ['E3', 'E-3', 'E3 Visa', 'E-3 Visa', 'Australian'],
  'US_CITIZEN':     ['US Citizen', 'U.S. Citizen', 'Citizen', 'United States Citizen',
                     'American Citizen', 'USC', 'US Citizen / Permanent Resident'],
  'GREEN_CARD':     ['Green Card', 'Permanent Resident', 'LPR', 'PR',
                     'Lawful Permanent Resident', 'I-551', 'Permanent Resident (Green Card)'],
  'CONDITIONAL_GC': ['Conditional Green Card', 'Conditional Permanent Resident',
                     'I-551 (Conditional)', 'Conditional LPR'],
  'PENDING_GC_EAD': ['EAD', 'Pending Green Card', 'Adjustment of Status',
                     'EAD (Pending GC)', 'I-485 EAD', 'Pending Permanent Residence'],
  'ASYLUM_EAD':     ['Asylum', 'Refugee', 'EAD (Asylum)', 'EAD (Refugee)',
                     'Asylee', 'Refugee Status', 'Asylum/Refugee'],
  'DACA':           ['DACA', 'DACA/EAD', 'Deferred Action', 'DACA Recipient'],
  'NON_IMMIGRANT':  ['Non-immigrant Visa', 'Non-immigrant', 'Visa Holder',
                     'Sponsored Worker', 'Working Holiday', 'Working Holiday Visa'],
  'OTHER':          ['Other', 'Other Visa', 'Not Listed', 'Other Status', 'Other Authorization'],
  'PREFER_NOT':     ['Prefer not to say', 'Prefer not to answer', 'Decline to answer',
                     'Choose not to answer', 'Decline to Self Identify'],
};

const VISA_EXPLANATIONS = {
  'F1':             'I am currently on an F1 student visa. I will require CPT authorization for internships and OPT authorization for full-time employment.',
  'F1_OPT':         'I am currently on F1 OPT status. I am authorized to work full-time and do not require immediate sponsorship, though I will need H1B sponsorship in the future.',
  'F1_STEM_OPT':    'I am currently on a STEM OPT extension. I am authorized to work full-time for up to 3 years and will require H1B sponsorship thereafter.',
  'J1':             'I am on a J1 exchange visitor visa and will require Academic Training authorization for internships.',
  'H1B':            'I am currently on an H1B visa and will require sponsorship transfer to join your organization.',
  'H4_EAD':         'I hold an H4 EAD which authorizes me to work in the US without direct sponsorship.',
  'L1':             'I am currently on an L1 visa through an intracompany transfer and will require sponsorship to change employers.',
  'O1':             'I am on an O1 visa for individuals with extraordinary ability and will require sponsorship transfer.',
  'TN':             'I am on a TN visa and will require TN status renewal to continue employment. No H1B sponsorship is needed.',
  'E3':             'I am on an E3 visa (Australian) and will require E3 renewal to continue employment.',
  'US_CITIZEN':     'I am a US citizen and am fully authorized to work in the United States without any sponsorship.',
  'GREEN_CARD':     'I am a permanent resident (Green Card holder) and am fully authorized to work in the United States without sponsorship.',
  'CONDITIONAL_GC': 'I hold a conditional green card and am authorized to work in the United States. I do not require sponsorship.',
  'PENDING_GC_EAD': 'I have a pending green card application with an EAD that authorizes me to work in the US while my application is processed.',
  'ASYLUM_EAD':     'I hold an EAD based on asylum/refugee status and am authorized to work in the United States.',
  'DACA':           'I am a DACA recipient with an EAD authorizing me to work in the United States.',
  'NON_IMMIGRANT':  'I am currently on a non-immigrant work visa and am authorized to work in the United States. I will require sponsorship to maintain my authorization.',
  'OTHER':          'I am currently on a student visa (F1) and will require CPT authorization for internships and OPT authorization for full-time employment.',
  'PREFER_NOT':     'I am currently on a student visa (F1) and will require CPT authorization for internships and OPT authorization for full-time employment.',
};

// Per visa type: are you authorized NOW vs LONG TERM
const VISA_WORK_AUTH = {
  'F1':             { now: 'Yes', longterm: 'No' },
  'F1_OPT':         { now: 'Yes', longterm: 'No' },
  'F1_STEM_OPT':    { now: 'Yes', longterm: 'No' },
  'J1':             { now: 'Yes', longterm: 'No' },
  'H1B':            { now: 'Yes', longterm: 'Yes' },
  'H4_EAD':         { now: 'Yes', longterm: 'No' },
  'L1':             { now: 'Yes', longterm: 'No' },
  'O1':             { now: 'Yes', longterm: 'No' },
  'TN':             { now: 'Yes', longterm: 'No' },
  'E3':             { now: 'Yes', longterm: 'No' },
  'US_CITIZEN':     { now: 'Yes', longterm: 'Yes' },
  'GREEN_CARD':     { now: 'Yes', longterm: 'Yes' },
  'CONDITIONAL_GC': { now: 'Yes', longterm: 'Yes' },
  'PENDING_GC_EAD': { now: 'Yes', longterm: 'No' },
  'ASYLUM_EAD':     { now: 'Yes', longterm: 'No' },
  'DACA':           { now: 'Yes', longterm: 'No' },
  'NON_IMMIGRANT':  { now: 'Yes', longterm: 'No' },
  'OTHER':          { now: 'Yes', longterm: 'No' },
  'PREFER_NOT':     { now: 'Yes', longterm: 'No' },
};

const DECLINE_SYNONYMS = [
  'Decline To Self Identify',
  'Decline to Self-Identify',
  "Don't wish to answer",
  'Prefer not to say',
  'Decline to answer',
  'Choose not to answer',
];

const US_STATES = {
  'AL': 'Alabama', 'AK': 'Alaska', 'AZ': 'Arizona', 'AR': 'Arkansas',
  'CA': 'California', 'CO': 'Colorado', 'CT': 'Connecticut', 'DE': 'Delaware',
  'FL': 'Florida', 'GA': 'Georgia', 'HI': 'Hawaii', 'ID': 'Idaho',
  'IL': 'Illinois', 'IN': 'Indiana', 'IA': 'Iowa', 'KS': 'Kansas',
  'KY': 'Kentucky', 'LA': 'Louisiana', 'ME': 'Maine', 'MD': 'Maryland',
  'MA': 'Massachusetts', 'MI': 'Michigan', 'MN': 'Minnesota', 'MS': 'Mississippi',
  'MO': 'Missouri', 'MT': 'Montana', 'NE': 'Nebraska', 'NV': 'Nevada',
  'NH': 'New Hampshire', 'NJ': 'New Jersey', 'NM': 'New Mexico', 'NY': 'New York',
  'NC': 'North Carolina', 'ND': 'North Dakota', 'OH': 'Ohio', 'OK': 'Oklahoma',
  'OR': 'Oregon', 'PA': 'Pennsylvania', 'RI': 'Rhode Island', 'SC': 'South Carolina',
  'SD': 'South Dakota', 'TN': 'Tennessee', 'TX': 'Texas', 'UT': 'Utah',
  'VT': 'Vermont', 'VA': 'Virginia', 'WA': 'Washington', 'WV': 'West Virginia',
  'WI': 'Wisconsin', 'WY': 'Wyoming', 'DC': 'District of Columbia',
};

const FIELD_PATTERNS = {
  // Basic fields
  first_name:               { patterns: [/first.?name/i, /given.?name/i],
                              neg: [/last/i, /preferred/i, /emergency/i, /reference/i] },
  last_name:                { patterns: [/last.?name/i, /surname/i, /family.?name/i],
                              neg: [/first/i, /emergency/i, /reference/i] },
  full_name:                { patterns: [/^name$/i, /full.?name/i, /your name/i],
                              neg: [/first/i, /last/i, /preferred/i, /company/i] },
  email:                    { patterns: [/e-?mail/i],
                              neg: [/confirm/i, /emergency/i, /reference/i] },
  phone:                    { patterns: [/phone/i, /mobile/i, /\btel\b/i],
                              neg: [/emergency/i, /fax/i, /reference/i] },
  linkedin:                 { patterns: [/linked.?in/i] },
  github:                   { patterns: [/git.?hub/i] },
  portfolio:                { patterns: [/portfolio/i, /personal.?site/i, /\bwebsite\b/i],
                              neg: [/company/i, /employer/i] },
  location_city:            { patterns: [/\bcity\b/i, /\btown\b/i],
                              neg: [/country/i, /state/i, /zip/i, /postal/i] },
  location_state:           { patterns: [/\bstate\b/i, /\bprovince\b/i],
                              neg: [/country/i, /city/i, /zip/i] },
  location_country:         { patterns: [/\bcountry\b/i],
                              neg: [/city/i, /state/i] },
  location_address:         { patterns: [/street.?address/i, /\baddress\b/i],
                              neg: [/city/i, /state/i, /country/i, /zip/i] },
  location_zip:             { patterns: [/\bzip\b/i, /postal.?code/i] },
  preferred_name:           { patterns: [/preferred.{0,10}name/i, /goes.?by/i, /nickname/i] },
  pronouns:                 { patterns: [/pronoun/i] },

  // Work authorization & immigration
  work_authorized:          { patterns: [/legally authorized/i, /authorized to work/i,
                                         /eligible to work/i, /right to work/i,
                                         /permitted to work/i, /us citizen or.*green card/i,
                                         /citizen or permanent/i],
                              neg: [/sponsor/i, /explain/i, /detail/i, /describe/i,
                                    /status/i, /type/i, /visa/i, /long.?term/i,
                                    /without sponsorship/i, /permanent/i] },
  work_authorized_longterm: { patterns: [/long.?term/i, /without sponsorship/i,
                                         /permanent.*auth/i, /eligible.*long/i,
                                         /work.*without.*requiring/i,
                                         /citizen or permanent resident/i],
                              neg: [/sponsor.*require/i, /explain/i, /detail/i, /describe/i] },
  needs_sponsorship:        { patterns: [/require.*sponsor/i, /need.*sponsor/i,
                                         /visa sponsor/i, /immigration support/i,
                                         /immigration assistance/i, /work authorization support/i,
                                         /now or in the future.*sponsor/i,
                                         /sponsor.*now or in the future/i],
                              neg: [/explain/i, /detail/i, /describe/i, /list/i, /status/i, /type/i] },
  visa_status:              { patterns: [/visa status/i, /work authorization status/i,
                                         /immigration status/i, /current.*visa/i,
                                         /type of.*visa/i, /type of.*authorization/i,
                                         /work auth.*type/i] },
  immigration_explanation:  { patterns: [/explain.*work auth/i, /describe.*visa/i,
                                         /detail.*immigration/i, /work authorization.*detail/i,
                                         /please (explain|describe).*(auth|visa|immigration)/i,
                                         /additional.*immigration/i, /immigration.*information/i,
                                         /immigration support.*if yes/i,
                                         /if yes.*please list/i,
                                         /need.*immigration support.*detail/i] },

  // EEO
  eeo_gender:               { patterns: [/\bgender\b/i, /gender identity/i],
                              neg: [/race/i, /ethnicity/i, /veteran/i, /disability/i] },
  eeo_race:                 { patterns: [/\brace\b/i, /racial/i, /ethnicity/i, /identify your race/i],
                              neg: [/gender/i, /veteran/i, /disability/i, /hispanic/i] },
  eeo_hispanic:             { patterns: [/hispanic/i, /latino/i] },
  eeo_veteran:              { patterns: [/veteran/i, /military/i, /armed forces/i, /protected veteran/i],
                              neg: [/disability/i, /gender/i] },
  eeo_disability:           { patterns: [/disability/i, /disabled/i, /disability status/i],
                              neg: [/veteran/i, /gender/i] },

  // Education
  school:                   { patterns: [/\bschool\b/i, /\buniversity\b/i, /\bcollege\b/i,
                                         /institution/i, /alma mater/i],
                              neg: [/degree/i, /major/i, /gpa/i, /high school/i] },
  degree:                   { patterns: [/\bdegree\b/i, /degree type/i, /level of education/i,
                                         /highest.*education/i, /education level/i],
                              neg: [/school/i, /major/i, /field/i, /discipline/i] },
  major:                    { patterns: [/\bmajor\b/i, /field of study/i, /\bdiscipline\b/i,
                                         /concentration/i, /area of study/i],
                              neg: [/school/i, /degree/i] },
  gpa:                      { patterns: [/\bgpa\b/i, /grade point/i, /cumulative.*grade/i] },
  graduation_date:          { patterns: [/graduation/i, /grad.?date/i, /expected.*grad/i,
                                         /end date/i, /completion date/i, /graduate.*when/i] },

  // Job specific
  compensation:             { patterns: [/compensation/i, /\bsalary\b/i, /\bpay\b/i,
                                         /hourly/i, /\bwage\b/i, /pay expectation/i],
                              neg: [/equity/i, /bonus/i, /benefit/i] },
  start_date:               { patterns: [/when can you start/i, /available to start/i,
                                         /start date/i, /earliest.*start/i],
                              neg: [/internship/i, /term/i] },
  years_experience:         { patterns: [/years.*experience/i, /experience.*years/i,
                                         /how many years/i] },
  internship_duration:      { patterns: [/how long.*internship/i, /internship.*duration/i,
                                         /internship.*length/i, /length.*internship/i] },
  internship_start:         { patterns: [/start.*internship/i, /internship.*start/i,
                                         /when.*start.*intern/i, /term.*start/i,
                                         /internship.*term/i] },
  internship_field:         { patterns: [/^what field.*internship/i, /^internship.*field/i,
                                         /^area.*internship/i, /^internship.*area/i] },
  previously_employed:      { patterns: [/previously employed/i, /worked (here|with us|for us)/i,
                                         /former.*employee/i, /worked for.*company/i] },
  referral:                 { patterns: [/who referred/i, /\breferral\b/i, /referred by/i],
                              neg: [/hear about/i, /learn about/i] },
  cover_letter:             { patterns: [/cover.?letter/i] },

  // Documents (file uploads)
  transcript_undergrad:     { patterns: [/undergrad(uate)?.*transcript/i,
                                         /transcript.*undergrad(uate)?/i,
                                         /unofficial.*transcript/i,
                                         /^transcript$/i],
                              neg: [/grad(uate)?(?!.*under)/i] },
  transcript_grad:          { patterns: [/grad(uate)?.*transcript/i,
                                         /transcript.*grad(uate)?/i,
                                         /graduate.*transcript/i],
                              neg: [/undergrad/i, /unofficial/i] },
};

const QUESTION_ALIASES = [
  { pattern: /how did you (learn|find out|hear) about/i,        canonical: 'where did you hear about' },
  { pattern: /where did you (learn|find out) about/i,           canonical: 'where did you hear about' },
  { pattern: /will you (be located|relocate|work) in.*area/i,   canonical: 'are you able to commute' },
  { pattern: /located in the .* area for the duration/i,        canonical: 'are you able to commute' },
  { pattern: /expected (compensation|salary|pay)/i,             canonical: 'compensation expectations' },
  { pattern: /desired (compensation|salary|pay)/i,              canonical: 'compensation expectations' },
  { pattern: /current (visa|immigration|work auth) status/i,    canonical: 'visa status' },
  { pattern: /when are you available to start/i,                canonical: 'what term were you looking to start' },
  { pattern: /what is your availability/i,                      canonical: 'are you available to work full time' },
  { pattern: /do you now or in the future.*require.*sponsor/i,  canonical: 'immigration support' },
  { pattern: /will you.*require.*sponsor.*future/i,             canonical: 'immigration support' },
  { pattern: /are you a us citizen or (green card|permanent)/i, canonical: 'work authorized longterm' },
  { pattern: /eligible.*long.?term basis/i,                     canonical: 'work authorized longterm' },
  { pattern: /authorized to work in the (us|united states)/i,   canonical: 'work authorization' },
  { pattern: /preferred first name/i,                           canonical: 'preferred name' },
  { pattern: /goes by/i,                                        canonical: 'preferred name' },
];

// ── Section 2: DOM Utilities ──────────────────────────────────────────────────

function humanDelay(min, max) {
  return new Promise(resolve => setTimeout(resolve, min + Math.random() * (max - min)));
}

function waitFor(getter, timeout) {
  timeout = timeout || 2000;
  return new Promise(function (resolve) {
    var start = Date.now();
    (function tick() {
      var v = null;
      try { v = getter(); } catch (e) {}
      if (v) return resolve(v);
      if (Date.now() - start > timeout) return resolve(null);
      setTimeout(tick, 80);
    })();
  });
}

// Gets label text for a single input element.
// Priority: aria-labelledby → aria-label → label[for] → wrapping label → DOM walk up
function getLabelForEl(el) {
  // 1. aria-labelledby — most explicit
  const labelledBy = el.getAttribute('aria-labelledby');
  if (labelledBy) {
    const text = labelledBy.split(' ')
      .map(id => document.getElementById(id)?.innerText?.trim())
      .filter(Boolean)
      .join(' ');
    if (text) return text;
  }

  // 2. aria-label
  const ariaLabel = el.getAttribute('aria-label');
  if (ariaLabel) return ariaLabel.trim();

  // 3. label[for] pointing to this element's id
  if (el.id) {
    const byFor = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (byFor) return byFor.innerText.trim();
  }

  // 4. Wrapping label — input is inside a label element
  const wrappingLabel = el.closest('label');
  if (wrappingLabel) {
    // Return only text nodes inside label, not the input's own value
    return Array.from(wrappingLabel.childNodes)
      .filter(n => n.nodeType === Node.TEXT_NODE)
      .map(n => n.textContent.trim())
      .filter(Boolean)
      .join(' ');
  }

  // 5. Walk up DOM looking for a heading/label sibling or parent text
  let node = el.parentElement;
  for (let i = 0; i < 5 && node; i++) {
    // Check for legend (fieldset question label)
    const legend = node.querySelector(':scope > legend');
    if (legend) return legend.innerText.trim();

    // Check for a label sibling that has a `for` pointing here OR has no input inside
    for (const lbl of node.querySelectorAll(':scope > label')) {
      if (lbl.getAttribute('for') === el.id) return lbl.innerText.trim();
      if (!lbl.querySelector('input, select, textarea, [role="combobox"]')) {
        const t = lbl.innerText.trim();
        if (t) return t;
      }
    }

    // Check for heading sibling
    const heading = node.querySelector(':scope > h1, :scope > h2, :scope > h3, :scope > h4');
    if (heading) return heading.innerText.trim();

    // Check for a <p> or <span> sibling with no inputs
    for (const el2 of node.querySelectorAll(':scope > p, :scope > span')) {
      if (!el2.querySelector('input, select, textarea, [role="combobox"]')) {
        const t = el2.innerText.trim();
        if (t) return t;
      }
    }

    node = node.parentElement;
  }

  return '';
}

// Gets label for a radio/checkbox group given its `name` attribute.
// Walks up from the first input in the group looking for a legend or heading.
function getLabelForGroup(inputs) {
  if (!inputs.length) return '';
  let node = inputs[0].parentElement;
  for (let i = 0; i < 8 && node; i++) {
    const legend = node.querySelector(':scope > legend');
    if (legend) return legend.innerText.trim();

    const heading = node.querySelector(':scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > p, :scope > span');
    if (heading && !heading.querySelector('input, select, textarea')) {
      const t = heading.innerText.trim();
      if (t) return t;
    }

    // If we hit a fieldset, stop — legend should have been found already
    if (node.tagName === 'FIELDSET') break;
    node = node.parentElement;
  }
  return '';
}

// Returns the input type string for a single element
function getInputType(el) {
  if (el.tagName === 'SELECT')   return 'native_select';
  if (el.tagName === 'TEXTAREA') return 'textarea';
  if (el.type === 'radio')       return 'radio';
  if (el.type === 'checkbox')    return 'checkbox';
  if (el.type === 'file')        return 'file';
  if (el.getAttribute('role') === 'combobox') return 'combobox';
  return 'text';
}

// Classifies a field — returns "category__inputType" or null
function classifyField(label, inputType) {
  if (!label || !inputType) return null;
  // Strip asterisks, required markers, and trailing punctuation before matching
  const searchText = label.replace(/[*†‡]/g, '').trim().toLowerCase();

  for (const [category, def] of Object.entries(FIELD_PATTERNS)) {
    if (!def.patterns.length) continue;
    const matched = def.patterns.some(p => p.test(searchText));
    if (!matched) continue;
    const blocked = def.neg && def.neg.some(p => p.test(searchText));
    if (blocked) continue;
    return `${category}__${inputType}`;
  }
  return null;
}

// Checks if a single input is already filled
function isInputFilled(el) {
  if (el.type === 'radio' || el.type === 'checkbox') return el.checked;
  if (el.tagName === 'SELECT') return !!el.value;
  if (el.getAttribute('role') === 'combobox') {
    const singleValue = el.closest('.select__container, .select__wrapper, div')
      ?.querySelector('.select__single-value');
    return !!(singleValue?.textContent?.trim());
  }
  return !!el.value;
}

// Collects all (label, inputType, element, groupKey) tuples from the page.
// Uses label-first traversal — no dependency on container class names.
function collectFields() {
  const seen = new Set(); // deduplicate by element reference
  const fields = [];

  function add(label, inputType, el, groupEls) {
    if (!label || !inputType || inputType === 'file') return;
    const key = groupEls ? groupEls[0] : el;
    if (seen.has(key)) return;
    seen.add(key);
    fields.push({ label: label.trim(), inputType, el, groupEls: groupEls || null });
  }

  // Strategy 1: labels with `for` attr → find their input
  for (const label of document.querySelectorAll('label[for]')) {
    const targetId = label.getAttribute('for');
    const el = document.getElementById(targetId);
    if (!el) continue;
    const inputType = getInputType(el);
    add(label.innerText.trim(), inputType, el, null);
  }

  // Strategy 2: radio groups — group by name, find group label
  const radioGroups = {};
  for (const el of document.querySelectorAll('input[type="radio"]')) {
    const name = el.name || el.id;
    if (!radioGroups[name]) radioGroups[name] = [];
    radioGroups[name].push(el);
  }
  for (const [, inputs] of Object.entries(radioGroups)) {
    const label = getLabelForGroup(inputs);
    add(label, 'radio', inputs[0], inputs);
  }

  // Strategy 3: checkbox groups — group by name
  const checkboxGroups = {};
  for (const el of document.querySelectorAll('input[type="checkbox"]')) {
    const name = el.name || el.id;
    if (!checkboxGroups[name]) checkboxGroups[name] = [];
    checkboxGroups[name].push(el);
  }
  for (const [, inputs] of Object.entries(checkboxGroups)) {
    const label = getLabelForGroup(inputs);
    add(label, 'checkbox', inputs[0], inputs);
  }

  // Strategy 4: inputs with aria-labelledby
  for (const el of document.querySelectorAll('[aria-labelledby]')) {
    if (el.type === 'radio' || el.type === 'checkbox' || el.type === 'file') continue;
    const label = getLabelForEl(el);
    add(label, getInputType(el), el, null);
  }

  // Strategy 5: wrapping labels (label wraps the input)
  for (const label of document.querySelectorAll('label:not([for])')) {
    const el = label.querySelector('input:not([type="radio"]):not([type="checkbox"]):not([type="file"]), select, textarea, [role="combobox"]');
    if (!el) continue;
    const labelText = Array.from(label.childNodes)
      .filter(n => n.nodeType === Node.TEXT_NODE)
      .map(n => n.textContent.trim())
      .filter(Boolean)
      .join(' ');
    add(labelText, getInputType(el), el, null);
  }

  // Strategy 6: inputs with aria-label only (no label element)
  // Restrict to actual form inputs — exclude buttons, links, and other interactive elements
  // that carry aria-label for accessibility but are not form fields
  for (const el of document.querySelectorAll('input[aria-label], textarea[aria-label], select[aria-label], [role="combobox"][aria-label]')) {
    if (el.type === 'radio' || el.type === 'checkbox' || el.type === 'file') continue;
    const label = el.getAttribute('aria-label').trim();
    add(label, getInputType(el), el, null);
  }

  // Strategy 7: fieldsets with legends (catch anything missed above)
  for (const fieldset of document.querySelectorAll('fieldset')) {
    const legend = fieldset.querySelector(':scope > legend');
    if (!legend) continue;
    const label = legend.innerText.trim();
    // Find the primary input inside
    const radio = fieldset.querySelector('input[type="radio"]');
    if (radio && !seen.has(radio)) {
      const inputs = Array.from(fieldset.querySelectorAll('input[type="radio"]'));
      add(label, 'radio', radio, inputs);
      continue;
    }
    const checkbox = fieldset.querySelector('input[type="checkbox"]');
    if (checkbox && !seen.has(checkbox)) {
      const inputs = Array.from(fieldset.querySelectorAll('input[type="checkbox"]'));
      add(label, 'checkbox', checkbox, inputs);
      continue;
    }
    const other = fieldset.querySelector('input:not([type="file"]), select, textarea, [role="combobox"]');
    if (other && !seen.has(other)) {
      add(label, getInputType(other), other, null);
    }
  }

  return fields;
}

// ── Section 3: Fill Mechanisms ────────────────────────────────────────────────

// Moves mouse to element in human-like steps
function moveToElement(element) {
  const rect = element.getBoundingClientRect();
  const targetX = rect.left + rect.width / 2;
  const targetY = rect.top + rect.height / 2;
  const startX = Math.random() * window.innerWidth;
  const startY = Math.random() * window.innerHeight;
  const steps = 5 + Math.floor(Math.random() * 4);
  for (let i = 1; i <= steps; i++) {
    document.dispatchEvent(new MouseEvent('mousemove', {
      bubbles: true,
      clientX: startX + (targetX - startX) * (i / steps),
      clientY: startY + (targetY - startY) * (i / steps),
    }));
  }
}

async function clickElement(element) {
  moveToElement(element);
  await humanDelay(50, 150);
  element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
  await humanDelay(30, 80);
  element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
  await humanDelay(20, 50);
  element.click();
}

// Fills a text input or textarea using native setter so React/Vue register the change
function _fillTextEl(el, value) {
  const proto = el instanceof HTMLTextAreaElement
    ? HTMLTextAreaElement.prototype
    : HTMLInputElement.prototype;
  const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;
  nativeSetter.call(el, value);
  el.dispatchEvent(new Event('input',  { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  el.dispatchEvent(new Event('blur',   { bubbles: true }));
}

async function fillTextField(container, value) {
  const el = container.querySelector(
    'input[type="text"], input[type="email"], input[type="tel"], input:not([type]), textarea'
  );
  if (!el || el.value) return false;
  _fillTextEl(el, value);
  return true;
}

async function fillNativeSelect(container, value, synonyms) {
  const el = container.querySelector('select');
  if (!el) return false;

  const candidates = [value, ...(synonyms || [])];
  for (const candidate of candidates) {
    const lower = candidate.toLowerCase();
    const opt = Array.from(el.options).find(o => {
      const t = o.text.toLowerCase();
      return t === lower || t.includes(lower) || lower.includes(t);
    });
    if (opt) {
      el.value = opt.value;
      el.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    }
  }
  return false;
}

async function fillReactCombobox(container, value, synonyms) {
  const el = container.querySelector('[role="combobox"]');
  if (!el) return false;

  const control = el.closest('.select__control');
  if (!control) return false;

  ['mousedown', 'mouseup', 'click'].forEach(type =>
    control.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }))
  );
  el.focus();

  // Scope listbox via aria-controls to avoid portal leakage from other comboboxes
  const listbox = await waitFor(() => {
    if (el.getAttribute('aria-expanded') !== 'true') return null;
    const id = el.getAttribute('aria-controls') || el.getAttribute('aria-owns');
    return id ? document.getElementById(id) : null;
  }, 2000);

  if (!listbox) return false;

  const options = Array.from(listbox.querySelectorAll('[role="option"]'));
  const candidates = [value, ...(synonyms || [])];
  let match = null;

  for (const candidate of candidates) {
    const lower = candidate.toLowerCase();
    match = options.find(o => {
      const t = o.textContent.trim().toLowerCase();
      return t === lower || t.includes(lower) || lower.includes(t);
    });
    if (match) break;
  }

  if (!match) {
    el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    console.log('filler: combobox no match for:', value, '| options:', options.map(o => o.textContent.trim()));
    return false;
  }

  ['mousedown', 'mouseup', 'click'].forEach(type =>
    match.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }))
  );
  await humanDelay(150, 250);
  return true;
}

// Type-to-search combobox — options load dynamically as you type (e.g. school field)
async function fillTypeaheadCombobox(container, value) {
  const el = container.querySelector('[role="combobox"]');
  if (!el) return false;

  const control = el.closest('.select__control');
  if (control) {
    ['mousedown', 'mouseup', 'click'].forEach(t =>
      control.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window }))
    );
  }
  el.focus();

  // Type first 8 chars to trigger search
  const nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  nativeSetter.call(el, value.slice(0, 8));
  el.dispatchEvent(new Event('input',  { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));

  // Wait for options to populate via aria-controls
  const listboxId = await waitFor(
    () => el.getAttribute('aria-controls') || el.getAttribute('aria-owns'), 2000
  );
  const listbox = listboxId ? await waitFor(() => {
    const lb = document.getElementById(listboxId);
    return lb && lb.querySelector('[role="option"]') ? lb : null;
  }, 3000) : null;

  if (!listbox) {
    console.log('filler: typeahead — listbox did not populate for:', value);
    return false;
  }

  const options = Array.from(listbox.querySelectorAll('[role="option"]'));
  const needle = value.toLowerCase();
  const match = options.find(o => {
    const t = o.textContent.trim().toLowerCase();
    return t === needle || t.includes(needle) || needle.includes(t);
  });

  if (!match) {
    el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    console.log('filler: typeahead — no match for:', value);
    return false;
  }

  ['mousedown', 'mouseup', 'click'].forEach(t =>
    match.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window }))
  );
  await humanDelay(150, 250);
  return true;
}

async function fillRadioGroup(container, value, synonyms) {
  const radios = Array.from(container.querySelectorAll('input[type="radio"]'));
  if (!radios.length) return false;

  const candidates = [value, ...(synonyms || [])];
  for (const candidate of candidates) {
    const lower = candidate.toLowerCase();
    const match = radios.find(r => {
      const labelEl = r.closest('label') ||
                      document.querySelector(`label[for="${r.id}"]`);
      const text = (labelEl?.textContent || r.value || '').toLowerCase();
      return text.includes(lower) || lower.includes(text);
    });
    if (match) {
      if (match.checked) return true;
      await clickElement(match);
      return true;
    }
  }
  return false;
}

async function fillCheckboxGroup(container, values) {
  const checkboxes = Array.from(container.querySelectorAll('input[type="checkbox"]'));
  if (!checkboxes.length) return false;

  let anyFilled = false;
  for (const value of (Array.isArray(values) ? values : [values])) {
    const lower = value.toLowerCase();
    const match = checkboxes.find(cb => {
      const labelEl = cb.closest('label') ||
                      document.querySelector(`label[for="${cb.id}"]`);
      const text = (labelEl?.textContent || cb.value || '').toLowerCase();
      return text.includes(lower) || lower.includes(text);
    });
    if (match && !match.checked) {
      await clickElement(match);
      anyFilled = true;
    }
  }
  return anyFilled;
}

// intl-tel-input phone field — fill country code then phone number
async function fillIntlPhone(container, countryName, phoneNumber) {
  const itiBtn = container.querySelector('button.iti__selected-country') ||
                 document.querySelector('button.iti__selected-country');
  if (itiBtn) {
    itiBtn.click();
    await humanDelay(200, 300);
    const listbox = await waitFor(
      () => document.querySelector('[id$="__country-listbox"]'), 2000
    );
    if (listbox) {
      const options = Array.from(listbox.querySelectorAll('[role="option"]'));
      const match = options.find(o => o.textContent.trim().startsWith(countryName));
      if (match) {
        match.click();
        await humanDelay(200, 300);
      }
    }
  }

  const phoneEl = container.querySelector('input[type="tel"], input[type="text"]');
  if (phoneEl && phoneNumber) {
    _fillTextEl(phoneEl, phoneNumber);
  }
  return true;
}

async function fillFileInput(inputEl, docType) {
  const result = await new Promise(resolve => {
    chrome.runtime.sendMessage({ type: 'fetch_document', doc_type: docType }, response => {
      if (chrome.runtime.lastError || !response?.ok || !response.data) return resolve(null);
      const binary = atob(response.data);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      resolve(new Blob([bytes], { type: 'application/pdf' }));
    });
  });

  if (!result) {
    console.log('filler: document not available —', docType);
    return false;
  }

  const filename = docType.replace('_', '-') + '.pdf';
  const file = new File([result], filename, { type: 'application/pdf' });
  const dt = new DataTransfer();
  dt.items.add(file);
  inputEl.files = dt.files;
  inputEl.dispatchEvent(new Event('change', { bubbles: true }));
  console.log('filler: file uploaded —', docType);
  return true;
}

// ── Section 4: Value Resolver ─────────────────────────────────────────────────

function normalizeQ(text) {
  return text.toLowerCase().replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();
}

function findCustomAnswer(labelText, customAnswers) {
  const needle = normalizeQ(labelText);

  // Check aliases first
  for (const alias of QUESTION_ALIASES) {
    if (alias.pattern.test(labelText)) {
      const canonicalNeedle = normalizeQ(alias.canonical);
      const ca = customAnswers.find(a => normalizeQ(a.questionKey) === canonicalNeedle);
      if (ca) return ca;
    }
  }

  // Fuzzy match
  let best = null, bestScore = 0;
  for (const ca of customAnswers) {
    const key = normalizeQ(ca.questionKey);
    if (needle.includes(key) || key.includes(needle)) {
      const score = key.length;
      if (score > bestScore) { bestScore = score; best = ca; }
    }
  }
  return bestScore >= 6 ? best : null;
}

// Returns { value, synonyms } or null
function resolveValue(classifiedCategory, profile, context) {
  const [category, inputType] = classifiedCategory.split('__');
  const customAnswers = Array.isArray(profile.custom_answers) ? profile.custom_answers : [];
  const prevEmployers = Array.isArray(profile.previous_employers) ? profile.previous_employers : [];

  const stateAbbr  = profile.location_state || '';
  const stateFull  = US_STATES[stateAbbr] || stateAbbr;
  const visaType   = profile.visa_type || 'OTHER';
  const visaAliases = VISA_ALIASES[visaType] || VISA_ALIASES['OTHER'];

  switch (category) {
    // Basic fields
    case 'first_name':
      return profile.first_name ? { value: profile.first_name, synonyms: [] } : null;
    case 'last_name':
      return profile.last_name ? { value: profile.last_name, synonyms: [] } : null;
    case 'full_name':
      return (profile.first_name && profile.last_name)
        ? { value: `${profile.first_name} ${profile.last_name}`, synonyms: [] } : null;
    case 'email':
      return profile.email ? { value: profile.email, synonyms: [] } : null;
    case 'phone':
      return profile.phone ? { value: profile.phone, synonyms: [] } : null;
    case 'linkedin':
      return profile.linkedin_url ? { value: profile.linkedin_url, synonyms: [] } : null;
    case 'github':
      return profile.github_url ? { value: profile.github_url, synonyms: [] } : null;
    case 'portfolio':
      return profile.portfolio_url ? { value: profile.portfolio_url, synonyms: [] } : null;
    case 'location_city':
      return profile.location_city ? { value: profile.location_city, synonyms: [] } : null;
    case 'location_state':
      return stateFull ? { value: stateFull, synonyms: [stateAbbr] } : null;
    case 'location_country':
      return profile.location_country ? { value: profile.location_country, synonyms: ['US', 'USA', 'United States of America'] } : null;
    case 'location_address':
      return profile.location_address ? { value: profile.location_address, synonyms: [] } : null;
    case 'location_zip':
      return profile.location_zip ? { value: profile.location_zip, synonyms: [] } : null;
    case 'preferred_name':
      return profile.preferred_name
        ? { value: profile.preferred_name, synonyms: [] }
        : profile.first_name ? { value: profile.first_name, synonyms: [] } : null;
    case 'pronouns':
      return profile.pronouns ? { value: profile.pronouns, synonyms: [] } : null;

    // Work authorization
    case 'work_authorized': {
      const authMap = VISA_WORK_AUTH[visaType] || VISA_WORK_AUTH['OTHER'];
      const isAuth = authMap.now === 'Yes';
      return {
        value: authMap.now,
        synonyms: isAuth
          ? ['Yes, I am authorized', 'Authorized', 'I am authorized', 'I am legally authorized']
          : ['No, I am not authorized'],
      };
    }
    case 'work_authorized_longterm': {
      const authMap = VISA_WORK_AUTH[visaType] || VISA_WORK_AUTH['OTHER'];
      const isLongterm = authMap.longterm === 'Yes';
      return {
        value: authMap.longterm,
        synonyms: isLongterm
          ? ['Yes, I am permanently authorized', 'Citizen or Permanent Resident']
          : ['No, I will require sponsorship in the future', 'No'],
      };
    }
    case 'needs_sponsorship': {
      const needsSpons = profile.needs_sponsorship === true || profile.needs_sponsorship === 'true';
      // Textarea variant: return the full visa explanation instead of Yes/No
      if (inputType === 'textarea' || inputType === 'text') {
        const explanation = VISA_EXPLANATIONS[visaType] || VISA_EXPLANATIONS['OTHER'];
        return { value: explanation, synonyms: [] };
      }
      return {
        value: needsSpons ? 'Yes' : 'No',
        synonyms: needsSpons
          ? ['Yes, I will require', 'Yes, I need sponsorship']
          : ['No, I will not', 'No, I do not need sponsorship'],
      };
    }
    case 'visa_status':
      return visaAliases.length
        ? { value: visaAliases[0], synonyms: visaAliases.slice(1) }
        : null;
    case 'immigration_explanation': {
      const explanation = VISA_EXPLANATIONS[visaType] || VISA_EXPLANATIONS['OTHER'];
      return { value: explanation, synonyms: [] };
    }

    // EEO
    case 'eeo_gender':
      return profile.eeo_gender
        ? { value: profile.eeo_gender, synonyms: DECLINE_SYNONYMS } : null;
    case 'eeo_race':
      return profile.eeo_race
        ? { value: profile.eeo_race, synonyms: DECLINE_SYNONYMS } : null;
    case 'eeo_hispanic': {
      const isHispanic = profile.eeo_hispanic === true || profile.eeo_hispanic === 'true';
      return {
        value: isHispanic ? 'Yes' : 'No',
        synonyms: isHispanic
          ? ['Yes, Hispanic or Latino']
          : ['No, not Hispanic or Latino'],
      };
    }
    case 'eeo_veteran':
      return profile.eeo_veteran ? {
        value: profile.eeo_veteran,
        synonyms: ['I am not a protected veteran', 'Not a protected veteran',
                   'I identify as a member of none of the listed veteran categories'],
      } : null;
    case 'eeo_disability':
      return profile.eeo_disability ? {
        value: profile.eeo_disability,
        synonyms: ["I don't have a disability", 'No, I do not have a disability', 'No'],
      } : null;

    // Education
    case 'school':
      return profile.school ? { value: profile.school, synonyms: [] } : null;
    case 'degree':
      return profile.degree ? {
        value: profile.degree,
        synonyms: ["Bachelor's Degree", 'Bachelor of Science', 'B.S.',
                   'Bachelors', 'Undergraduate', 'BA', 'Bachelor of Arts'],
      } : null;
    case 'major':
      return profile.major ? {
        value: profile.major,
        synonyms: ['Computer Science', 'CS', 'Computing', 'Software Engineering'],
      } : null;
    case 'gpa': {
      if (!profile.gpa) return null;
      const gpa = parseFloat(profile.gpa);
      // Build synonyms covering common dropdown bucket formats
      const synonyms = [];
      if (gpa >= 3.9)       synonyms.push('3.9', '4.0', '3.9 - 4.0', '3.9+');
      if (gpa >= 3.5)       synonyms.push('3.5', '3.5 - 4.0', '3.5 - 3.9', '3.5+', '3.5 or above', '3.50');
      if (gpa >= 3.0)       synonyms.push('3.0', '3.0 - 3.49', '3.0 - 3.5', '3.0+', '3.00');
      if (gpa >= 2.5)       synonyms.push('2.5', '2.5 - 2.99', '2.5 - 3.0', '2.50');
      synonyms.push(String(profile.gpa));
      return { value: synonyms[0], synonyms: synonyms.slice(1) };
    }
    case 'graduation_date': {
      if (!profile.graduation_date) return null;
      const parts = profile.graduation_date.split(' ');
      const month = parts[0];
      const year  = parts[parts.length - 1];
      // Pass both — fill mechanism decides based on field count in container
      return { value: profile.graduation_date, synonyms: [], month, year };
    }

    // Job specific
    case 'compensation': {
      // 1. Parse salary/hourly range from page DOM (JD is rendered on the same page)
      const pageText = document.body.innerText || '';
      // Matches patterns like "$48 – $56", "$48-$56", "$48 - $56/hr", "$85,000 - $120,000"
      const rangeMatch = pageText.match(/\$(\d[\d,]*)\s*[-–—]\s*\$(\d[\d,]*)/);
      if (rangeMatch) {
        const lo = Number(rangeMatch[1].replace(/,/g, ''));
        const hi = Number(rangeMatch[2].replace(/,/g, ''));
        if (lo > 0 && hi > 0) {
          const midpoint = Math.round((lo + hi) / 2);
          return { value: String(midpoint), synonyms: [], isFreeText: true };
        }
      }

      // 2. No JD range found — check if field is free text or requires a number
      // Resolved at fill time: if textarea/text → use open-ended string
      // If combobox/select → use profile midpoint as fallback
      const profileMidpoint = (profile.desired_hourly_min && profile.desired_hourly_max)
        ? String(Math.round((Number(profile.desired_hourly_min) + Number(profile.desired_hourly_max)) / 2))
        : null;

      return {
        value: 'Open to standard market compensation',
        synonyms: [],
        numericFallback: profileMidpoint,
      };
    }
    case 'internship_duration': {
      const ca = findCustomAnswer('how long of an internship', customAnswers);
      return ca ? { value: [ca.answer], synonyms: [] } : null; // array for checkbox
    }
    case 'internship_start': {
      const ca = findCustomAnswer('what term were you looking to start', customAnswers);
      return ca ? { value: ca.answer, synonyms: ['Summer 2026', 'Fall 2026', 'Spring 2027'] } : null;
    }
    case 'internship_field': {
      const ca = findCustomAnswer('what field are you looking to complete your internship', customAnswers);
      return ca ? { value: ca.answer, synonyms: ['Software Development', 'Engineering', 'Software'] } : null;
    }
    case 'start_date': {
      const ca = findCustomAnswer('what term were you looking to start', customAnswers);
      return ca ? { value: ca.answer, synonyms: [] } : null;
    }
    case 'years_experience': {
      const ca = findCustomAnswer('years of experience', customAnswers);
      return ca ? { value: ca.answer, synonyms: [] } : null;
    }
    case 'previously_employed': {
      const companyName = (context && context.job && context.job.company_name) || '';
      const wasEmployed = prevEmployers.some(emp =>
        companyName.toLowerCase().includes(emp.toLowerCase()) ||
        emp.toLowerCase().includes(companyName.toLowerCase())
      );
      return {
        value: wasEmployed ? 'Yes' : 'No',
        synonyms: [],
      };
    }
    case 'cover_letter': {
      // Only fill free-text cover letter fields — file upload variants are skipped
      if (inputType !== 'text' && inputType !== 'textarea') return null;
      const ca = findCustomAnswer('cover letter', customAnswers);
      return ca ? { value: ca.answer, synonyms: [] } : null;
    }
    case 'transcript_undergrad':
      return inputType === 'file' ? { value: 'transcript_undergrad', synonyms: [] } : null;
    case 'transcript_grad':
      return inputType === 'file' ? { value: 'transcript_grad', synonyms: [] } : null;
    case 'referral': {
      const ca = findCustomAnswer('where did you hear about', customAnswers);
      return ca ? { value: ca.answer, synonyms: ['Other'] } : null;
    }

    default:
      return null;
  }
}

// ── Section 5: Main Loop ──────────────────────────────────────────────────────

// Fills a single field given its classified category, input type, element, and group
async function fillField(field, classified, profile, context) {
  const [category, inputType] = classified.split('__');
  const resolved = resolveValue(classified, profile, context);

  if (!resolved) {
    console.log('filler: no value resolved for:', classified, '|', field.label.slice(0, 50));
    return false;
  }

  const { value, synonyms } = resolved;

  // Special case: school uses typeahead combobox
  if (category === 'school' && inputType === 'combobox') {
    const container = field.el.closest('div, fieldset') || document.body;
    return await fillTypeaheadCombobox(container, value);
  }

  // Special case: phone uses intl-tel-input
  if (category === 'phone') {
    const container = field.el.closest('div, fieldset') || document.body;
    return await fillIntlPhone(container, profile.location_country || 'United States', value);
  }

  // Special case: graduation_date — check if there are two comboboxes (month + year)
  if (category === 'graduation_date' && inputType === 'combobox' && resolved.month && resolved.year) {
    const container = field.el.closest('div, fieldset') || document.body;
    const comboboxes = container.querySelectorAll('[role="combobox"]');
    if (comboboxes.length >= 2) {
      const c1 = comboboxes[0].closest('div') || container;
      const c2 = comboboxes[1].closest('div') || container;
      await fillReactCombobox(c1, resolved.month, []);
      await humanDelay(100, 200);
      await fillReactCombobox(c2, resolved.year, []);
      return true;
    }
  }

  // Special case: compensation — use numericFallback for non-text fields
  let fillValue = value;
  if (category === 'compensation' && resolved.numericFallback) {
    if (inputType === 'combobox' || inputType === 'native_select') {
      fillValue = resolved.numericFallback;
    }
    // text/textarea gets the open-ended string value as-is
  }

  // Standard dispatch by input type
  // For group fields (radio/checkbox), we need the container to find all inputs
  const container = (field.groupEls
    ? field.groupEls[0].closest('fieldset, div, li') || document.body
    : field.el.closest('div, fieldset') || document.body
  );

  switch (inputType) {
    case 'text':
    case 'textarea': {
      if (field.el instanceof HTMLInputElement || field.el instanceof HTMLTextAreaElement) {
        _fillTextEl(field.el, fillValue);
        return true;
      }
      // contenteditable div (rich text editors like cover letter)
      if (field.el.isContentEditable || field.el.getAttribute('contenteditable') === 'true') {
        field.el.focus();
        field.el.innerText = fillValue;
        field.el.dispatchEvent(new Event('input',  { bubbles: true }));
        field.el.dispatchEvent(new Event('change', { bubbles: true }));
        return true;
      }
      // Try finding an input/textarea inside the container as a last resort
      const inner = container.querySelector('input[type="text"], input:not([type]), textarea');
      if (inner) { _fillTextEl(inner, fillValue); return true; }
      console.log('filler: skipping non-input element for text fill —', field.label.slice(0, 50));
      return false;
    }
    case 'native_select':
      return await fillNativeSelect(container, fillValue, synonyms);
    case 'combobox':
      return await fillReactCombobox(container, fillValue, synonyms);
    case 'radio':
      return await fillRadioGroup(container, fillValue, synonyms);
    case 'checkbox':
      return await fillCheckboxGroup(container, Array.isArray(fillValue) ? fillValue : [fillValue]);
    default:
      return false;
  }
}

// Waits for DOM to stabilize after fills trigger conditional field reveals.
// Scoped to formEl only — ignores mutations from outside the form.
// Disconnects before resolving so pass 2 fills don't re-trigger it.
function waitForDomStability(formEl, hardTimeoutMs) {
  return new Promise(resolve => {
    let timer = setTimeout(() => { observer.disconnect(); resolve(); }, hardTimeoutMs || 3000);

    const observer = new MutationObserver(() => {
      clearTimeout(timer);
      timer = setTimeout(() => { observer.disconnect(); resolve(); }, 500);
    });

    observer.observe(formEl, { childList: true, subtree: true });
  });
}

// One pass — collect all fields, classify, resolve, fill
async function runPass(profile, context, atsConfig, seenEls) {
  const fields = collectFields();
  let newCount = 0;

  for (const field of fields) {
    // Skip already processed elements
    if (seenEls.has(field.el)) continue;

    // Skip already filled
    if (isInputFilled(field.el)) {
      seenEls.add(field.el);
      continue;
    }

    // Handle file inputs — classify by label, upload if known doc type, skip otherwise
    if (field.inputType === 'file') {
      if (field.label) {
        const classified = classifyField(field.label, 'file');
        if (classified) {
          const [category] = classified.split('__');
          const resolved = resolveValue(classified, profile, context);
          if (resolved) {
            await fillFileInput(field.el, resolved.value);
          }
        } else {
          console.log('filler: unclassified file input —', field.label.slice(0, 80));
        }
      }
      seenEls.add(field.el);
      continue;
    }

    // Skip if no label
    if (!field.label) { seenEls.add(field.el); continue; }

    newCount++;

    // Try classifier
    let classified = classifyField(field.label, field.inputType);

    if (classified) {
      const ok = await fillField(field, classified, profile, context);
      console.log(
        ok ? 'filler: filled' : 'filler: fill failed',
        '—', classified, '|', field.label.slice(0, 60)
      );
    } else {
      // Tier 1 fallback: custom_answers fuzzy match
      const customAnswers = Array.isArray(profile.custom_answers) ? profile.custom_answers : [];
      const ca = findCustomAnswer(field.label, customAnswers);

      if (ca) {
        if (field.inputType === 'text' || field.inputType === 'textarea') {
          _fillTextEl(field.el, ca.answer);
        } else if (field.inputType === 'combobox') {
          const container = field.el.closest('div, fieldset') || document.body;
          await fillReactCombobox(container, ca.answer, ['Other']);
        } else if (field.inputType === 'radio') {
          const container = field.groupEls
            ? field.groupEls[0].closest('fieldset, div') || document.body
            : field.el.closest('div, fieldset') || document.body;
          await fillRadioGroup(container, ca.answer, []);
        } else if (field.inputType === 'native_select') {
          const container = field.el.closest('div, fieldset') || document.body;
          await fillNativeSelect(container, ca.answer, []);
        }
        console.log('filler: custom answer —', field.label.slice(0, 60), '→', ca.answer.slice(0, 40));
      } else {
        // Tier 2: log and skip
        console.log('filler: no match —', field.label.slice(0, 80), '| type:', field.inputType);
      }
    }

    seenEls.add(field.el);
    await humanDelay(80, 150);
  }

  return newCount;
}

// Main entry point — called by each ATS content script
async function runFillerLoop(profile, context, atsConfig) {
  const MAX_PASSES = 3;
  const formEl = atsConfig.form || document.body;
  const seenEls = new Set(); // tracks processed input elements across passes

  for (let pass = 1; pass <= MAX_PASSES; pass++) {
    console.log(`filler: starting pass ${pass}`);
    const newCount = await runPass(profile, context, atsConfig, seenEls);
    console.log(`filler: pass ${pass} complete — ${newCount} new fields processed`);

    if (pass < MAX_PASSES) {
      if (newCount === 0) {
        console.log('filler: no new fields found — stopping early');
        break;
      }
      // Wait for DOM to stabilize before next pass
      await waitForDomStability(formEl, atsConfig.stabilityTimeoutMs || 3000);
    }
  }
}
