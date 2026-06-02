// Ashby application form filler.
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

  // ── Human timing utilities ─────────────────────────────────────────────────
  function humanDelay(min, max) {
    return new Promise(resolve =>
      setTimeout(resolve, min + Math.random() * (max - min))
    );
  }

  // Ashby is React — use native setter so React's synthetic event system fires.
  const _nativeSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, 'value'
  ).set;

  async function humanType(element, text) {
    for (let i = 0; i < text.length; i++) {
      if (Math.random() < 0.03) {
        const wrong = String.fromCharCode(97 + Math.floor(Math.random() * 26));
        _nativeSetter.call(element, element.value + wrong);
        element.dispatchEvent(new Event('input', { bubbles: true }));
        await humanDelay(50, 180);
        _nativeSetter.call(element, element.value.slice(0, -1));
        element.dispatchEvent(new Event('input', { bubbles: true }));
        await humanDelay(50, 180);
      }
      _nativeSetter.call(element, element.value + text[i]);
      element.dispatchEvent(new Event('input', { bubbles: true }));
      await humanDelay(50, 180);
      const chunkSize = 8 + Math.floor(Math.random() * 8);
      if (i > 0 && i % chunkSize === 0) {
        await humanDelay(200, 800);
      }
    }
  }

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

  async function focusField(element) {
    moveToElement(element);
    element.dispatchEvent(new FocusEvent('focus', { bubbles: true }));
    await humanDelay(50, 150);
    element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    await humanDelay(30, 80);
    element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    element.click();
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

  // ── Handshake with background ──────────────────────────────────────────────
  // Ashby is a React SPA — wait longer than Greenhouse for initial render.
  await humanDelay(3000, 5000);

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
  } catch {
    return exit();
  }

  if (!context || !context.job) return exit();

  const { job, auto_submit, needs_sponsorship, user_id,
          first_name, last_name, email, phone, linkedin_url, location_city } = context;

  function send(msg) {
    chrome.runtime.sendMessage(msg);
  }

  // ── Wait for React to render the form ─────────────────────────────────────
  const form = await new Promise(resolve => {
    const deadline = Date.now() + 10000;
    const poll = setInterval(() => {
      const f =
        document.querySelector('form') ||
        document.querySelector('[data-testid="application-form"]') ||
        document.querySelector('[class*="ApplicationForm"]');
      if (f || Date.now() > deadline) {
        clearInterval(poll);
        resolve(f || null);
      }
    }, 300);
  });

  if (!form) {
    send({ type: 'needs_review', reason: 'not_a_standard_ashby_form' });
    return exit();
  }

  const fileInputs = form.querySelectorAll('input[type="file"]');
  if (fileInputs.length > 1) {
    send({ type: 'needs_review', reason: 'multiple_file_uploads' });
    return exit();
  }

  // ── Fill fields ────────────────────────────────────────────────────────────
  await humanDelay(1000, 3000);

  // First name
  const firstNameEl = findField(
    'input[name="firstName"]', 'input[name="first_name"]',
    'input[autocomplete="given-name"]'
  ) || findFieldByLabelText('first name');
  if (firstNameEl && first_name) {
    await focusField(firstNameEl);
    await humanType(firstNameEl, first_name);
  }

  // Last name
  const lastNameEl = findField(
    'input[name="lastName"]', 'input[name="last_name"]',
    'input[autocomplete="family-name"]'
  ) || findFieldByLabelText('last name');
  if (lastNameEl && last_name) {
    await focusField(lastNameEl);
    await humanType(lastNameEl, last_name);
  }

  // Some Ashby forms use a single "Full Name" field instead of first/last
  if (!firstNameEl && !lastNameEl && first_name && last_name) {
    const fullNameEl = findFieldByLabelText('full name') || findFieldByLabelText('your name');
    if (fullNameEl) {
      await focusField(fullNameEl);
      await humanType(fullNameEl, `${first_name} ${last_name}`);
    }
  }

  // Email
  const emailEl = findField(
    'input[name="email"]', 'input[type="email"]',
    'input[autocomplete="email"]'
  ) || findFieldByLabelText('email');
  if (emailEl && email) {
    await focusField(emailEl);
    await humanType(emailEl, email);
  }

  // Phone
  const phoneEl = findField(
    'input[name="phone"]', 'input[type="tel"]',
    'input[autocomplete="tel"]'
  ) || findFieldByLabelText('phone');
  if (phoneEl && phone) {
    await focusField(phoneEl);
    await humanType(phoneEl, phone);
  }

  // LinkedIn URL
  const linkedInEl = findNearText('linkedin', 'input') || findFieldByLabelText('linkedin');
  if (linkedInEl && linkedin_url) {
    await focusField(linkedInEl);
    await humanType(linkedInEl, linkedin_url);
  }

  // Location / city
  const locationEl = findField(
    'input[name="location"]', 'input[name="city"]'
  ) || findFieldByLabelText('location') || findFieldByLabelText('city');
  if (locationEl && location_city) {
    await focusField(locationEl);
    await humanType(locationEl, location_city);
  }

  // ── Resume upload ──────────────────────────────────────────────────────────
  const resumeInput =
    form.querySelector('input[type="file"][name*="resume" i]') ||
    form.querySelector('input[type="file"]');

  if (resumeInput) {
    const blob = await getResumePdf(job.job_id, job.job_ats);
    if (!blob) {
      send({ type: 'failed', reason: 'resume_pdf_unavailable' });
      return exit();
    }

    const file = new File([blob], 'resume.pdf', { type: 'application/pdf' });
    const dt = new DataTransfer();
    dt.items.add(file);
    resumeInput.files = dt.files;
    resumeInput.dispatchEvent(new Event('change', { bubbles: true }));

    // Wait up to 3s for filename confirmation in DOM
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
  }

  // ── Work authorization ─────────────────────────────────────────────────────
  const authSelect = findField(
    'select[name*="authorization" i]',
    'select[name*="workAuth" i]',
    'select[name*="work_auth" i]'
  );
  if (authSelect) {
    const affirmative = Array.from(authSelect.options).find(o =>
      /yes|authorized|eligible/i.test(o.text)
    );
    if (affirmative) {
      authSelect.value = affirmative.value;
      authSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }
  } else {
    const authRadio = findNearText('authorized to work', 'input[type="radio"]') ||
                      findNearText('work authorization', 'input[type="radio"]');
    if (authRadio) {
      const container = authRadio.closest('fieldset, div[role="group"]');
      if (container) {
        const yesOption = Array.from(container.querySelectorAll('input[type="radio"]')).find(r =>
          /yes|authorized/i.test(r.closest('label, div')?.textContent || '')
        );
        if (yesOption) await clickElement(yesOption);
      }
    }
  }

  // ── Sponsorship ────────────────────────────────────────────────────────────
  const sponsorContainer = (() => {
    for (const el of document.querySelectorAll('fieldset, div')) {
      if (/sponsor/i.test(el.textContent) && el.querySelector('input[type="radio"]')) {
        return el;
      }
    }
    return null;
  })();

  if (sponsorContainer) {
    const keyword = needs_sponsorship ? /yes/i : /no/i;
    const option = Array.from(sponsorContainer.querySelectorAll('input[type="radio"]')).find(r =>
      keyword.test(r.closest('label, div')?.textContent || '')
    );
    if (option) await clickElement(option);
  }

  // ── Submit or hand off ─────────────────────────────────────────────────────
  await humanDelay(1000, 2000);

  if (!auto_submit) {
    send({ type: 'needs_review', reason: 'awaiting_user_submit' });
    return exit();
  }

  const submitBtn =
    form.querySelector('button[type="submit"]') ||
    form.querySelector('input[type="submit"]') ||
    Array.from(form.querySelectorAll('button')).find(b =>
      /submit/i.test(b.textContent)
    );

  if (!submitBtn) {
    send({ type: 'failed', reason: 'submit_button_not_found' });
    return exit();
  }

  await clickElement(submitBtn);

  // Ashby is a SPA — no URL change on success, watch for success text only.
  const confirmed = await new Promise(resolve => {
    const deadline = Date.now() + 10000;
    const poll = setInterval(() => {
      const successText = /thank you|application received|successfully submitted|application submitted/i;
      if (successText.test(document.body.textContent)) {
        clearInterval(poll);
        return resolve(true);
      }
      if (Date.now() > deadline) {
        clearInterval(poll);
        resolve(false);
      }
    }, 500);
  });

  if (confirmed) {
    send({ type: 'success' });
  } else {
    send({ type: 'failed', reason: 'submit_timeout' });
  }

  exit();
})();
