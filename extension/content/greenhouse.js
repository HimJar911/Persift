console.log('greenhouse.js injected');

// Greenhouse application form filler.
// api.js is injected before this script — getUserId, getResumePdf, etc. are globals.

(async function () {
  'use strict';

  // ── Heartbeat ──────────────────────────────────────────────────────────────
  const heartbeatTimer = setInterval(() => {
    chrome.runtime.sendMessage({ type: 'heartbeat' });
  }, 30000);

  function exit() {
    clearInterval(heartbeatTimer);
  }

  // ── Utilities ──────────────────────────────────────────────────────────────
  function humanDelay(min, max) {
    return new Promise(resolve =>
      setTimeout(resolve, min + Math.random() * (max - min))
    );
  }

  // Used only for radio buttons and submit — not text inputs.
  function moveToElement(element) {
    const rect = element.getBoundingClientRect();
    const targetX = rect.left + rect.width / 2;
    const targetY = rect.top + rect.height / 2;
    const startX = Math.random() * window.innerWidth;
    const startY = Math.random() * window.innerHeight;
    const steps = 5 + Math.floor(Math.random() * 4);
    for (let i = 1; i <= steps; i++) {
      const x = startX + (targetX - startX) * (i / steps);
      const y = startY + (targetY - startY) * (i / steps);
      document.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: x, clientY: y }));
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

  // Fills a text input in a way React/Vue/Angular actually registers.
  // Direct .value assignment bypasses framework state — must use the native prototype setter.
  function fillText(element, text) {
    const proto = element instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    nativeSetter.call(element, text);
    element.dispatchEvent(new Event('input',  { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
    element.dispatchEvent(new Event('blur',   { bubbles: true }));
  }

  // Polls until getter() returns a truthy value or timeout expires.
  function waitFor(getter, timeout) {
    timeout = timeout || 2000;
    return new Promise(function(resolve) {
      var start = Date.now();
      (function tick() {
        var v = null;
        try { v = getter(); } catch(e) {}
        if (v) return resolve(v);
        if (Date.now() - start > timeout) return resolve(null);
        setTimeout(tick, 80);
      })();
    });
  }

  // Opens a react-select combobox and returns its scoped listbox + options.
  // Scopes via aria-controls so portal menus from OTHER selects (e.g. country picker) are ignored.
  async function openReactSelect(inputEl) {
    var control = inputEl.closest('.select__control');
    if (!control) return null;

    ['mousedown', 'mouseup', 'click'].forEach(function(type) {
      control.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
    });
    inputEl.focus();

    var listbox = await waitFor(function() {
      if (inputEl.getAttribute('aria-expanded') !== 'true') return null;
      var id = inputEl.getAttribute('aria-controls') || inputEl.getAttribute('aria-owns');
      return id ? document.getElementById(id) : null;
    }, 2000);

    if (!listbox) return null;

    var options = Array.from(listbox.querySelectorAll('[role="option"]')).map(function(o) {
      return { text: o.textContent.trim(), el: o };
    });
    return { listbox: listbox, options: options };
  }

  // Fills a react-select by opening it and clicking the best-matching option.
  // synonyms: array of fallback strings to try if desiredText doesn't match.
  async function fillCombobox(inputEl, desiredText, synonyms) {
    if (!inputEl) return false;
    synonyms = synonyms || [];

    var opened = await openReactSelect(inputEl);
    if (!opened) {
      console.log('greenhouse: combobox — failed to open for:', desiredText);
      return false;
    }

    var candidates = [desiredText].concat(synonyms);
    var match = null;
    for (var i = 0; i < candidates.length; i++) {
      var needle = candidates[i].toLowerCase();
      match = opened.options.find(function(o) {
        var t = o.text.toLowerCase();
        return t === needle || t.includes(needle) || needle.includes(t);
      });
      if (match) break;
    }

    if (!match) {
      inputEl.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      console.log('greenhouse: combobox — no option matched for:', desiredText, '| available:', opened.options.map(function(o){return o.text;}));
      return false;
    }

    ['mousedown', 'mouseup', 'click'].forEach(function(type) {
      match.el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
    });
    await humanDelay(150, 250);
    console.log('greenhouse: combobox — selected:', match.text, 'for:', desiredText);
    return true;
  }

  // Finds a react-select combobox input by its associated label text.
  function findComboboxByLabel(labelText) {
    for (const label of document.querySelectorAll('label')) {
      if (label.textContent.toLowerCase().includes(labelText.toLowerCase())) {
        const id = label.getAttribute('for');
        if (id) {
          const el = document.getElementById(id);
          if (el && el.getAttribute('role') === 'combobox') return el;
        }
      }
    }
    return null;
  }

  function findField(...selectors) {
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) return el;
    }
    return null;
  }

  function findFieldByLabelText(text) {
    for (const label of document.querySelectorAll('label')) {
      if (label.textContent.toLowerCase().includes(text.toLowerCase())) {
        const id = label.getAttribute('for');
        if (id) return document.getElementById(id);
        return label.querySelector('input, select, textarea');
      }
    }
    return null;
  }

  function findNearText(text, inputType = 'input') {
    const els = document.querySelectorAll(inputType);
    for (const el of els) {
      const container = el.closest('div, fieldset, li');
      if (container && container.textContent.toLowerCase().includes(text.toLowerCase())) {
        return el;
      }
    }
    return null;
  }

  // ── Scoring classifier — fallback for fields our explicit selectors miss ──
  // Collects signals from each unfilled input, scores against field definitions,
  // returns the best match above a confidence threshold.

  const FIELD_DEFS = {
    firstName:  { autocomplete: ['given-name'],  patterns: [/first.?name/i, /given.?name/i, /\bfname\b/i], neg: [/last/i, /emergency/i, /reference/i, /preferred/i] },
    lastName:   { autocomplete: ['family-name'], patterns: [/last.?name/i, /surname/i, /family.?name/i],   neg: [/first/i, /emergency/i, /reference/i] },
    email:      { autocomplete: ['email'],        patterns: [/e-?mail/i],                                   neg: [/confirm/i, /reference/i, /emergency/i] },
    phone:      { autocomplete: ['tel'],          patterns: [/phone/i, /mobile/i, /\btel\b/i],              neg: [/emergency/i, /reference/i, /fax/i] },
    linkedin:   { patterns: [/linked.?in/i] },
    github:     { patterns: [/git.?hub/i] },
    portfolio:  { patterns: [/portfolio/i, /personal.?(web)?site/i] },
    location:   { autocomplete: ['address-level2', 'city'], patterns: [/\bcity\b/i, /location/i, /\btown\b/i], neg: [/country/i, /state/i, /zip/i] },
    preferredName: { patterns: [/preferred.?name/i, /goes by/i, /nickname/i] },
  };

  const WEIGHTS = { autocomplete: 100, label: 60, ariaLabel: 55, containerText: 35, name: 30, id: 25, placeholder: 15 };

  function getFieldSignals(el) {
    const labelEl = (el.labels && el.labels[0]) || document.querySelector(`label[for="${el.id}"]`);
    const container = el.closest('[class*="field"], [class*="question"], fieldset, .form-group, li, div');
    return {
      autocomplete: el.getAttribute('autocomplete') || '',
      label:        (labelEl?.innerText || '').trim(),
      ariaLabel:    el.getAttribute('aria-label') || '',
      containerText:(container?.innerText || '').slice(0, 200),
      name:         el.name || '',
      id:           el.id   || '',
      placeholder:  el.placeholder || '',
    };
  }

  function classifyField(el) {
    const s = getFieldSignals(el);
    const scores = {};
    for (const [fieldType, def] of Object.entries(FIELD_DEFS)) {
      let score = 0;
      if (def.autocomplete?.includes(s.autocomplete)) score += WEIGHTS.autocomplete;
      const checks = [['label', s.label], ['ariaLabel', s.ariaLabel], ['containerText', s.containerText], ['name', s.name], ['id', s.id], ['placeholder', s.placeholder]];
      for (const [key, text] of checks) {
        if (!text) continue;
        if (def.patterns?.some(p => p.test(text)))  score += WEIGHTS[key] || 10;
        if (def.neg?.some(p => p.test(text)))        score -= 80;
      }
      if (score > 0) scores[fieldType] = score;
    }
    const ranked = Object.entries(scores).sort((a, b) => b[1] - a[1]);
    return ranked.length && ranked[0][1] >= 40 ? ranked[0][0] : null;
  }

  // Maps classifier field type → value from context
  function resolveValue(fieldType, ctx) {
    const map = {
      firstName:     ctx.first_name,
      lastName:      ctx.last_name,
      email:         ctx.email,
      phone:         ctx.phone,
      linkedin:      ctx.linkedin_url,
      github:        ctx.github_url,
      location:      ctx.location_city,
      preferredName: ctx.preferred_name,
    };
    return map[fieldType] || null;
  }

  // ── Handshake with background ──────────────────────────────────────────────
  await humanDelay(2000, 2000);

  console.log('greenhouse: sending ready message');
  let context;
  try {
    context = await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('timeout')), 15000);
      chrome.runtime.sendMessage({ type: 'ready', url: location.href }, response => {
        clearTimeout(t);
        if (chrome.runtime.lastError) return reject(chrome.runtime.lastError);
        resolve(response);
      });
    });
  } catch (err) {
    console.log('greenhouse: ready handshake failed —', err && err.message);
    return exit();
  }

  console.log('greenhouse: context received —', JSON.stringify({ job_id: context?.job?.job_id, has_email: !!context?.email }));

  if (!context || !context.job) {
    console.log('greenhouse: context or context.job is null — exiting');
    return exit();
  }

  const { job, auto_submit, user_id,
          first_name, last_name, email, phone, linkedin_url, location_city,
          location_state, location_country, github_url, preferred_name,
          school, degree, major, gpa, graduation_date,
          eeo_gender, eeo_race, eeo_hispanic, eeo_veteran, eeo_disability,
          work_authorized, needs_sponsorship,
          desired_hourly_min, desired_hourly_max,
          custom_answers, previous_employers } = context;

  const customAnswers = Array.isArray(custom_answers) ? custom_answers : [];
  const prevEmployers = Array.isArray(previous_employers) ? previous_employers : [];

  function send(msg) {
    chrome.runtime.sendMessage(msg);
  }

  // ── Form detection ─────────────────────────────────────────────────────────
  const form =
    document.querySelector('#application_form') ||
    document.querySelector('form[action*="greenhouse"]') ||
    document.querySelector('form[id*="application"]');

  console.log('greenhouse: form detected —', form ? (form.id || form.action || 'yes') : 'null');

  if (!form) {
    send({ type: 'needs_review', reason: 'not_a_standard_greenhouse_form' });
    return exit();
  }

  const fileInputs = form.querySelectorAll('input[type="file"]');
  console.log('greenhouse: file inputs found —', fileInputs.length);
  Array.from(fileInputs).forEach((el, i) => {
    console.log(`greenhouse: file input [${i}] name=${el.name} id=${el.id} accept=${el.accept} class=${el.className}`);
  });
  const nonResumeFileInputs = Array.from(fileInputs).filter(
    el => !/resume/i.test((el.name || '') + ' ' + (el.id || ''))
  );
  console.log('greenhouse: nonResumeFileInputs —', nonResumeFileInputs.length, nonResumeFileInputs.map(el => el.id));
  if (nonResumeFileInputs.length > 1) {
    send({ type: 'needs_review', reason: 'multiple_file_uploads' });
    return exit();
  }

  // ── Fill fields ────────────────────────────────────────────────────────────
  await humanDelay(1000, 3000);

  // First name
  const firstNameEl = findField(
    '#first_name', 'input[name="job_application[first_name]"]',
    'input[autocomplete="given-name"]'
  ) || findFieldByLabelText('first name');
  console.log('greenhouse: first_name field —', firstNameEl ? 'found' : 'not found');
  if (firstNameEl && first_name) {
    fillText(firstNameEl, first_name);
    console.log('greenhouse: first_name filled');
  }

  // Last name
  const lastNameEl = findField(
    '#last_name', 'input[name="job_application[last_name]"]',
    'input[autocomplete="family-name"]'
  ) || findFieldByLabelText('last name');
  console.log('greenhouse: last_name field —', lastNameEl ? 'found' : 'not found');
  if (lastNameEl && last_name) {
    fillText(lastNameEl, last_name);
    console.log('greenhouse: last_name filled');
  }

  // Email
  const emailEl = findField(
    '#email', 'input[name="job_application[email]"]',
    'input[type="email"]', 'input[autocomplete="email"]'
  ) || findFieldByLabelText('email');
  console.log('greenhouse: email field —', emailEl ? 'found' : 'not found');
  if (emailEl && email) {
    fillText(emailEl, email);
    console.log('greenhouse: email filled');
  }

  // Phone country code — intl-tel-input library, must fill BEFORE phone number
  // Open button: button.iti__selected-country; listbox: iti-0__country-listbox
  // Option text format: "United States+1" (name + dial code, no space)
  console.log('greenhouse: filling phone country code');
  const itiBtn = document.querySelector('button.iti__selected-country');
  if (itiBtn) {
    itiBtn.click();
    await humanDelay(200, 300);
    const listbox = await waitFor(() => document.querySelector('[id$="__country-listbox"]'), 2000);
    if (listbox) {
      const options = Array.from(listbox.querySelectorAll('[role="option"]'));
      const match = options.find(o => o.textContent.trim().startsWith('United States'));
      if (match) {
        match.click();
        await humanDelay(200, 300);
        console.log('greenhouse: country code filled — United States');
      } else {
        console.log('greenhouse: country code — United States not found, count:', options.length);
      }
    } else {
      console.log('greenhouse: country code — listbox did not appear');
    }
  } else {
    console.log('greenhouse: country code — iti button not found');
  }

  // Phone
  const phoneEl = findField(
    '#phone', 'input[name="job_application[phone]"]',
    'input[type="tel"]', 'input[autocomplete="tel"]'
  ) || findFieldByLabelText('phone');
  console.log('greenhouse: phone field —', phoneEl ? 'found' : 'not found');
  if (phoneEl && phone) {
    fillText(phoneEl, phone);
    console.log('greenhouse: phone filled');
  }

  // LinkedIn URL
  const linkedInEl = findNearText('linkedin', 'input') || findFieldByLabelText('linkedin');
  console.log('greenhouse: linkedin field —', linkedInEl ? 'found' : 'not found');
  if (linkedInEl && linkedin_url) {
    fillText(linkedInEl, linkedin_url);
    console.log('greenhouse: linkedin filled');
  }

  // Location / city
  const locationEl = findField(
    '#job_application_location', 'input[name="job_application[location]"]'
  ) || findFieldByLabelText('location') || findFieldByLabelText('city');
  console.log('greenhouse: location field —', locationEl ? 'found' : 'not found');
  if (locationEl && location_city) {
    fillText(locationEl, location_city);
    console.log('greenhouse: location filled');
  }

  // ── Resume upload ──────────────────────────────────────────────────────────
  const resumeInput =
    form.querySelector('input[type="file"][id*="resume" i]') ||
    form.querySelector('input[type="file"][name*="resume" i]') ||
    form.querySelector('input[type="file"]');

  console.log('greenhouse: resume input —', resumeInput ? 'found' : 'not found');

  if (resumeInput) {
    console.log('greenhouse: fetching resume PDF via background');
    const blob = await new Promise(resolve => {
      chrome.runtime.sendMessage({ type: 'fetch_resume', job_id: job.job_id, job_ats: job.job_ats }, response => {
        if (chrome.runtime.lastError || !response?.ok || !response.data) return resolve(null);
        const binary = atob(response.data);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
        resolve(new Blob([bytes], { type: 'application/pdf' }));
      });
    });
    console.log('greenhouse: resume PDF —', blob ? `${blob.size} bytes` : 'null');
    if (!blob) {
      send({ type: 'failed', reason: 'resume_pdf_unavailable' });
      return exit();
    }

    const file = new File([blob], 'resume.pdf', { type: 'application/pdf' });
    const dt = new DataTransfer();
    dt.items.add(file);
    resumeInput.files = dt.files;
    resumeInput.dispatchEvent(new Event('change', { bubbles: true }));

    await new Promise(resolve => {
      let elapsed = 0;
      const poll = setInterval(() => {
        elapsed += 200;
        const confirmed =
          document.body.textContent.includes('resume.pdf') ||
          resumeInput.files.length > 0;
        if (confirmed || elapsed >= 3000) {
          clearInterval(poll);
          resolve();
        }
      }, 200);
    });
    console.log('greenhouse: resume upload complete');
  }

  // ── Work authorization ─────────────────────────────────────────────────────
  // Handles three cases: native <select>, radio group, react-select combobox
  console.log('greenhouse: checking work auth fields');
  const authSelect = findField('select[name*="authorization" i]');
  if (authSelect) {
    const affirmative = Array.from(authSelect.options).find(o =>
      /yes|authorized|eligible/i.test(o.text)
    );
    if (affirmative) {
      authSelect.value = affirmative.value;
      authSelect.dispatchEvent(new Event('change', { bubbles: true }));
      console.log('greenhouse: work auth select set to —', affirmative.text);
    }
  } else {
    const authRadio = findNearText('authorized to work', 'input[type="radio"]') ||
                      findNearText('work authorization', 'input[type="radio"]') ||
                      findNearText('legally authorized', 'input[type="radio"]');
    if (authRadio) {
      const container = authRadio.closest('fieldset, div[role="group"]');
      if (container) {
        const yesOption = Array.from(container.querySelectorAll('input[type="radio"]')).find(r =>
          /yes|authorized/i.test(r.closest('label, div')?.textContent || '')
        );
        if (yesOption) {
          await clickElement(yesOption);
          console.log('greenhouse: work auth radio clicked');
        }
      }
    } else {
      // React-select combobox path — use known field ID (question_15354233008 on this form)
      // then fall back to label scan for other Greenhouse forms
      const authCombobox = findComboboxByLabel('legally authorized') ||
                           findComboboxByLabel('authorized to work') ||
                           findComboboxByLabel('work authorization') ||
                           findComboboxByLabel('eligible to work in the us') ||
                           findComboboxByLabel('eligible to work in the united states') ||
                           findComboboxByLabel('work in the us on a long term');
      if (authCombobox) {
        const authAnswer = (work_authorized === 'true' || work_authorized === true) ? 'Yes' : 'No';
        await fillCombobox(authCombobox, authAnswer, ['Yes, I am authorized', 'Authorized']);
        console.log('greenhouse: work auth combobox filled —', authAnswer);
      } else {
        console.log('greenhouse: no work auth field found');
      }
    }
  }

  // ── Sponsorship ────────────────────────────────────────────────────────────
  console.log('greenhouse: checking sponsorship fields');
  const sponsorContainer = (() => {
    // Search only within the form, and only shallow containers (fieldset or div
    // that directly contains a radio — avoids matching job description text).
    const candidates = form.querySelectorAll('fieldset, div[class*="field"], div[class*="question"]');
    for (const el of candidates) {
      const radios = el.querySelectorAll('input[type="radio"]');
      if (radios.length === 0) continue;
      // Check the element's own direct text content, not all descendants
      const ownText = Array.from(el.childNodes)
        .filter(n => n.nodeType === Node.TEXT_NODE || n.nodeName === 'LABEL' || n.nodeName === 'LEGEND' || n.nodeName === 'P')
        .map(n => n.textContent).join(' ');
      if (/sponsor/i.test(ownText)) return el;
    }
    // Broader fallback — still scoped to form
    for (const el of form.querySelectorAll('fieldset')) {
      if (/sponsor/i.test(el.textContent) && el.querySelector('input[type="radio"]')) return el;
    }
    return null;
  })();

  if (sponsorContainer) {
    const keyword = needs_sponsorship ? /yes/i : /no/i;
    const option = Array.from(sponsorContainer.querySelectorAll('input[type="radio"]')).find(r =>
      keyword.test(r.closest('label, div')?.textContent || '')
    );
    if (option) {
      await clickElement(option);
      console.log('greenhouse: sponsorship radio clicked — needs_sponsorship:', needs_sponsorship);
    }
  } else {
    // React-select combobox path for sponsorship
    const sponsorCombobox = findComboboxByLabel('sponsorship') ||
                            findComboboxByLabel('visa') ||
                            findComboboxByLabel('immigration support') ||
                            findComboboxByLabel('immigration assistance') ||
                            findComboboxByLabel('work authorization support');
    if (sponsorCombobox) {
      await fillCombobox(sponsorCombobox, needs_sponsorship ? 'Yes' : 'No');
      console.log('greenhouse: sponsorship combobox filled — needs_sponsorship:', needs_sponsorship);
    } else {
      console.log('greenhouse: no sponsorship field found');
    }
  }

  // ── EEO fields ────────────────────────────────────────────────────────────
  // Handles both native <select> and react-select comboboxes.
  // synonyms array covers the variation in how employers phrase decline/prefer-not options.
  console.log('greenhouse: filling EEO fields');

  async function fillEeoField(fieldId, labelText, nativePattern, desired, synonyms) {
    // Try by direct ID first (most reliable on Greenhouse)
    var inputEl = fieldId ? document.getElementById(fieldId) : null;
    if (!inputEl) inputEl = findComboboxByLabel(labelText);

    if (inputEl && inputEl.getAttribute('role') === 'combobox') {
      var filled = await fillCombobox(inputEl, desired, synonyms);
      console.log('greenhouse: EEO', labelText, filled ? '— filled' : '— no match found');
      await humanDelay(150, 150);
      return;
    }

    // Native <select> fallback
    var selectEl = findFieldByLabelText(labelText);
    if (selectEl && selectEl.tagName === 'SELECT') {
      var opt = Array.from(selectEl.options).find(function(o) { return nativePattern.test(o.text); });
      if (opt) {
        selectEl.value = opt.value;
        selectEl.dispatchEvent(new Event('change', { bubbles: true }));
        console.log('greenhouse: EEO', labelText, '— native select —', opt.text);
      }
      return;
    }

    console.log('greenhouse: EEO', labelText, '— field not found');
  }

  var declineSynonyms = ['Decline To Self Identify', 'Decline to Self-Identify', "Don't wish to answer", 'Prefer not to say', 'Decline to answer', 'Choose not to answer'];

  // Use profile values — fall back to decline/no if not set
  var genderVal    = eeo_gender    || 'Decline To Self Identify';
  var raceVal      = eeo_race      || 'Decline To Self Identify';
  var hispanicVal  = (eeo_hispanic === 'true' || eeo_hispanic === true) ? 'Yes' : 'No';
  var veteranVal   = eeo_veteran   || 'I am not a protected veteran';
  var disabilityVal= eeo_disability|| "I don't have a disability";

  await fillEeoField('gender',            'gender',    /decline to self.identify/i, genderVal,    declineSynonyms);
  await fillEeoField('hispanic_ethnicity','hispanic',  /^no$/i,                     hispanicVal,  ['No, not Hispanic or Latino']);
  await fillEeoField(null,                'race',      /decline to self.identify/i, raceVal,      declineSynonyms);
  await fillEeoField('veteran_status',    'veteran',   /not a protected veteran/i,  veteranVal,   ['I am not a protected veteran', 'Not a protected veteran', 'No']);
  await fillEeoField('disability_status', 'disability',/don.t have a disability/i,  disabilityVal,["I don't have a disability", 'No, I do not have a disability', 'No']);

  // ── Classifier sweep — catch any remaining unfilled text inputs ────────────
  // Runs after all explicit selectors so it only touches what was missed.
  console.log('greenhouse: running classifier sweep');
  const ctx = { first_name, last_name, email, phone, linkedin_url, location_city, github_url, preferred_name };
  const allInputs = form.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"], input:not([type])');
  for (const el of allInputs) {
    if (el.value) continue; // already filled — don't overwrite
    if (el.getAttribute('role') === 'combobox') continue; // handled separately
    const fieldType = classifyField(el);
    if (!fieldType) continue;
    const value = resolveValue(fieldType, ctx);
    if (!value) continue;
    fillText(el, value);
    console.log('greenhouse: classifier filled', el.id || el.name, '→', fieldType);
  }

  // ── Education section ─────────────────────────────────────────────────────
  console.log('greenhouse: filling education fields');
  const schoolEl  = document.getElementById('school--0')  || findComboboxByLabel('school');
  const degreeEl  = document.getElementById('degree--0')  || findComboboxByLabel('degree');
  const disciplineEl = document.getElementById('discipline--0') || findComboboxByLabel('discipline') || findComboboxByLabel('field of study') || findComboboxByLabel('major');
  const endMonthEl = document.getElementById('end-month--0') || findComboboxByLabel('end date month') || findComboboxByLabel('graduation month');

  // End year — plain input or combobox
  const endYearEl = document.getElementById('end-year--0') ||
    document.querySelector('input[id*="end-year"]') ||
    document.querySelector('input[id*="end_year"]') ||
    findComboboxByLabel('end date year') || findComboboxByLabel('graduation year');

  if (schoolEl && school) {
    if (schoolEl.getAttribute('role') === 'combobox') {
      // Type-to-search: open dropdown, type to populate, then click matching option directly.
      // Do NOT call fillCombobox() — it re-opens the dropdown and loses the search results.
      const control = schoolEl.closest('.select__control');
      if (control) {
        ['mousedown', 'mouseup', 'click'].forEach(t =>
          control.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window }))
        );
      }
      schoolEl.focus();
      const nativeSetter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      nativeSetter.call(schoolEl, school.slice(0, 8));
      schoolEl.dispatchEvent(new Event('input', { bubbles: true }));
      schoolEl.dispatchEvent(new Event('change', { bubbles: true }));

      // Wait for options to populate
      const listboxId = await waitFor(() => schoolEl.getAttribute('aria-controls') || schoolEl.getAttribute('aria-owns'), 2000);
      const listbox = listboxId ? await waitFor(() => {
        const lb = document.getElementById(listboxId);
        return lb && lb.querySelector('[role="option"]') ? lb : null;
      }, 3000) : null;

      if (listbox) {
        const options = Array.from(listbox.querySelectorAll('[role="option"]'));
        console.log('greenhouse: school options —', options.map(o => o.textContent.trim()));
        const needle = school.toLowerCase();
        const match = options.find(o => {
          const t = o.textContent.trim().toLowerCase();
          return t === needle || t.includes(needle) || needle.includes(t);
        });
        if (match) {
          ['mousedown', 'mouseup', 'click'].forEach(t =>
            match.dispatchEvent(new MouseEvent(t, { bubbles: true, cancelable: true, view: window }))
          );
          await humanDelay(150, 250);
          console.log('greenhouse: school filled —', match.textContent.trim());
        } else {
          console.log('greenhouse: school — no match found for:', school);
        }
      } else {
        console.log('greenhouse: school — listbox did not populate after typing');
      }
    } else {
      fillText(schoolEl, school);
      console.log('greenhouse: school filled (text)');
    }
  }

  if (degreeEl && degree) {
    await fillCombobox(degreeEl, degree, ["Bachelor's Degree", "Bachelor of Science", "B.S.", "Bachelors"]);
    console.log('greenhouse: degree filled');
  }

  if (disciplineEl && major) {
    await fillCombobox(disciplineEl, major, ['Computer Science', 'CS', 'Computing']);
    console.log('greenhouse: discipline filled');
  }

  if (endMonthEl && graduation_date) {
    // graduation_date = "May 2027" — extract month
    const parts = graduation_date.split(' ');
    const monthName = parts[0];
    await fillCombobox(endMonthEl, monthName, []);
    console.log('greenhouse: end month filled —', monthName);
  }

  if (endYearEl && graduation_date) {
    const parts = graduation_date.split(' ');
    const year = parts[parts.length - 1];
    if (endYearEl.getAttribute('role') === 'combobox') {
      await fillCombobox(endYearEl, year, []);
    } else {
      fillText(endYearEl, year);
    }
    console.log('greenhouse: end year filled —', year);
  }

  // ── State & Country ────────────────────────────────────────────────────────
  // This is a free-text input on this form (not a combobox). Fill via findFieldByLabelText.
  console.log('greenhouse: filling state & country');
  const stateCountryVal = (location_state === 'AZ' ? 'Arizona' : location_state) + ', ' + location_country;
  const stateCountryTextEl =
    findFieldByLabelText('state & country') ||
    findFieldByLabelText('state and country') ||
    findFieldByLabelText('currently located') ||
    findFieldByLabelText('in which state') ||
    findNearText('currently located', 'input') ||
    findNearText('state & country', 'input') ||
    document.getElementById('state_and_country') ||
    document.querySelector('[id*="state_and_country"]') ||
    document.querySelector('[id*="state-and-country"]');
  if (stateCountryTextEl && stateCountryTextEl.getAttribute('role') !== 'combobox') {
    fillText(stateCountryTextEl, stateCountryVal);
    console.log('greenhouse: state & country text filled —', stateCountryVal);
  } else if (stateCountryTextEl) {
    // It is a combobox after all on this form variant
    await fillCombobox(stateCountryTextEl, stateCountryVal, [location_country, location_state, 'United States', 'Arizona, United States', 'Arizona']);
    console.log('greenhouse: state & country combobox filled —', stateCountryVal);
  } else {
    console.log('greenhouse: state & country — field not found');
  }

  // ── Internship duration checkboxes ────────────────────────────────────────
  // Find the "how long of an internship" question block, then tick the checkbox
  // matching our saved answer (e.g. "12 months"). Reads from custom_answers so
  // it stays in sync with the profile rather than being hardcoded.
  console.log('greenhouse: filling internship duration checkboxes');
  const durationAnswer = (() => {
    const ca = customAnswers.find(a => /how long of an internship/i.test(a.questionKey));
    return ca ? ca.answer.toLowerCase().trim() : null;
  })();
  if (durationAnswer) {
    // Find the question container by heading/legend text
    const allLabels = document.querySelectorAll('label');
    for (const lbl of allLabels) {
      const txt = lbl.textContent.trim().toLowerCase();
      if (txt === durationAnswer) {
        const cb = lbl.querySelector('input[type="checkbox"]') ||
                   document.getElementById(lbl.getAttribute('for'));
        if (cb && !cb.checked) {
          cb.click();
          console.log('greenhouse: internship duration checked —', durationAnswer);
        }
      }
    }
  }

  // ── Graduation date text field ─────────────────────────────────────────────
  console.log('greenhouse: filling graduation date text field');
  const gradDateEl = findNearText('expected date of graduation', 'input[type="text"]') ||
                     findNearText('expected graduation', 'input[type="text"]');
  if (gradDateEl && !gradDateEl.value && graduation_date) {
    fillText(gradDateEl, graduation_date);
    console.log('greenhouse: graduation date text filled —', graduation_date);
  }

  // ── Hourly compensation ────────────────────────────────────────────────────
  // Use profile min/max to compute midpoint. Falls back to custom_answers string.
  console.log('greenhouse: filling compensation');
  const compAnswer = (() => {
    if (desired_hourly_min && desired_hourly_max) {
      return String(Math.round((desired_hourly_min + desired_hourly_max) / 2));
    }
    const ca = customAnswers.find(a => /hourly compensation/i.test(a.questionKey));
    return ca ? ca.answer : null;
  })();
  if (compAnswer) {
    // Find compensation text input — look for question containing "hourly" + "compensation"
    const compEl = findNearText('hourly compensation', 'input[type="text"]') ||
                   findNearText('compensation expectations', 'input[type="text"]') ||
                   findNearText('expected compensation', 'input[type="text"]') ||
                   findNearText('pay expectation', 'input[type="text"]') ||
                   findNearText('salary expectation', 'input[type="text"]') ||
                   findNearText('desired compensation', 'input[type="text"]');
    if (compEl && !compEl.value) {
      fillText(compEl, compAnswer);
      console.log('greenhouse: compensation filled —', compAnswer);
    }
  }

  // ── Custom answers sweep ───────────────────────────────────────────────────
  // For every unfilled question on the form, check if we have a saved answer.
  // Matching is fuzzy — normalize both the question label and the saved questionKey.
  console.log('greenhouse: running custom answers sweep, answers available:', customAnswers.length);

  function normalizeQ(text) {
    return text.toLowerCase().replace(/[^a-z0-9 ]/g, '').replace(/\s+/g, ' ').trim();
  }

  // Semantic aliases — maps common question phrasings to a canonical key we have saved.
  // When a form label matches an alias, we look up the canonical key instead.
  const QUESTION_ALIASES = [
    { pattern: /how did you (learn|find out) about/i, canonical: 'where did you hear about' },
    { pattern: /where did you (learn|find out) about/i, canonical: 'where did you hear about' },
    { pattern: /how did you hear about/i, canonical: 'where did you hear about' },
    { pattern: /will you (be located|relocate|work) in.*area/i, canonical: 'are you able to commute' },
    { pattern: /located in the .* area for the duration/i, canonical: 'are you able to commute' },
    { pattern: /expected (compensation|salary|pay)/i, canonical: 'compensation expectations' },
    { pattern: /desired (compensation|salary|pay)/i, canonical: 'compensation expectations' },
    { pattern: /immigration support|visa support|work authorization support/i, canonical: 'were you previously employed' },
  ];

  function findCustomAnswer(labelText) {
    const needle = normalizeQ(labelText);

    // Check aliases first — remap label to canonical key if it matches
    for (const alias of QUESTION_ALIASES) {
      if (alias.pattern.test(labelText)) {
        const canonicalNeedle = normalizeQ(alias.canonical);
        const ca = customAnswers.find(a => normalizeQ(a.questionKey) === canonicalNeedle);
        if (ca) return ca;
      }
    }

    // Score each saved answer by how much of its key appears in the label
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

  function getLabelForEl(el) {
    const byFor = document.querySelector('label[for="' + el.id + '"]');
    if (byFor) return byFor.innerText.trim();
    const nearest = el.closest('[class*="field"], [class*="question"], fieldset, li, div');
    if (!nearest) return '';
    // Try <label> or <legend> first; fall back to any heading-like element
    const labelEl = nearest.querySelector('label, legend, p, h1, h2, h3, h4, span');
    return labelEl ? labelEl.innerText.trim() : nearest.innerText.slice(0, 150).trim();
  }

  // Text inputs and textareas — search document-wide, Greenhouse renders some questions outside <form>
  const customTextEls = document.querySelectorAll('input[type="text"], textarea');
  for (const el of customTextEls) {
    if (el.value) continue;
    if (el.getAttribute('role') === 'combobox') continue;
    const label = getLabelForEl(el);
    if (!label) continue;
    const match = findCustomAnswer(label);
    if (!match) continue;
    fillText(el, match.answer);
    console.log('greenhouse: custom answer filled —', label.slice(0, 60), '→', match.answer.slice(0, 40));
  }

  // Labels we've already handled explicitly — skip in the sweep to avoid overwriting.
  const handledLabels = /^(gender|hispanic|latino|race|ethnicity|veteran status|disability status|school|degree|discipline|field of study|major|end date|graduation month|graduation year|country|legally authorized|authorized to work|work authorization|sponsorship|visa)$/i;

  // Combobox dropdowns — search document-wide for same reason
  const allComboboxes = document.querySelectorAll('[role="combobox"]');
  console.log('greenhouse: combobox sweep — found', allComboboxes.length, 'comboboxes');
  for (const el of allComboboxes) {
    if (el.value) continue;
    const label = getLabelForEl(el);
    if (handledLabels.test(label.trim())) {
      console.log('greenhouse: combobox sweep — skipping already-handled:', label.slice(0, 50));
      continue;
    }
    console.log('greenhouse: combobox label —', JSON.stringify(label.slice(0, 80)));
    if (!label) continue;

    // Special case: "previously employed" — check against resume companies
    if (/previously employed|worked (here|with us|for us)/i.test(label)) {
      const companyName = job.company_name || '';
      const wasEmployed = prevEmployers.some(function(emp) {
        return companyName.toLowerCase().includes(emp.toLowerCase()) ||
               emp.toLowerCase().includes(companyName.toLowerCase());
      });
      await fillCombobox(el, wasEmployed ? 'Yes' : 'No', []);
      console.log('greenhouse: previously employed —', companyName, '→', wasEmployed ? 'Yes' : 'No');
      await humanDelay(150, 150);
      continue;
    }

    const match = findCustomAnswer(label);
    if (!match) continue;

    // Build smart synonyms for known problem cases
    const synonyms = [];
    if (/how did you hear|where did you hear/i.test(label)) {
      // If our saved answer isn't in the list, fall back to "Other"
      synonyms.push('Other');
    }
    if (/what field.*internship|internship.*field/i.test(label)) {
      // "Software Engineering" → try "Software Development" as synonym
      synonyms.push('Software Development', 'Engineering', 'Software');
    }
    if (/veteran of the armed forces/i.test(label)) {
      // Map "I identify as a member of none of the listed veteran categories" → "I am not a veteran"
      synonyms.push('I am not a veteran', 'I do not wish to answer', 'Not a veteran');
    }

    await fillCombobox(el, match.answer, synonyms);
    console.log('greenhouse: custom answer combobox —', label.slice(0, 50), '→', match.answer.slice(0, 40));
    await humanDelay(150, 150);
  }

  // ── Submit or hand off ────────────────────────────────────────────────────
  await humanDelay(1000, 2000);

  console.log('greenhouse: auto_submit —', auto_submit);

  if (!auto_submit) {
    send({ type: 'needs_review', reason: 'awaiting_user_submit' });
    return exit();
  }

  const submitBtn =
    form.querySelector('button[type="submit"]') ||
    form.querySelector('input[type="submit"]') ||
    document.querySelector('#submit_app');

  console.log('greenhouse: submit button —', submitBtn ? 'found' : 'not found');

  if (!submitBtn) {
    send({ type: 'failed', reason: 'submit_button_not_found' });
    return exit();
  }

  await clickElement(submitBtn);
  console.log('greenhouse: submit clicked — waiting for confirmation');

  const confirmed = await new Promise(resolve => {
    const deadline = Date.now() + 10000;
    const check = setInterval(() => {
      const successText = /thank you|application received|successfully submitted/i;
      const urlChanged = !location.href.includes('/application');
      if (successText.test(document.body.textContent) || urlChanged) {
        clearInterval(check);
        return resolve(true);
      }
      if (Date.now() > deadline) {
        clearInterval(check);
        resolve(false);
      }
    }, 500);
  });

  console.log('greenhouse: confirmation —', confirmed);

  if (confirmed) {
    send({ type: 'success' });
  } else {
    send({ type: 'failed', reason: 'submit_timeout' });
  }

  exit();
})();
