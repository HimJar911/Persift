console.log('greenhouse.js injected');

// Greenhouse application form filler.
// api.js and filler_utils.js are injected before this script — all utilities are globals.

(async function () {
  'use strict';

  // ── Heartbeat ──────────────────────────────────────────────────────────────
  const heartbeatTimer = setInterval(() => {
    chrome.runtime.sendMessage({ type: 'heartbeat' });
  }, 30000);

  function exit() { clearInterval(heartbeatTimer); }
  // job_id/job_ats travel with every message so background.js can identify
  // which job a stale tab is reporting on even after it's no longer
  // current_job (e.g. logging a genuine submit from a tab whose job was
  // already given up on / reassigned) instead of relying solely on in-memory
  // current_job, which a stale tab has no way to know has moved on.
  function send(msg) {
    chrome.runtime.sendMessage({
      ...msg,
      job_id: context?.job?.job_id,
      job_ats: context?.job?.job_ats,
    });
  }

  // ── Handshake ──────────────────────────────────────────────────────────────
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

  console.log('greenhouse: context received —', JSON.stringify({
    job_id: context?.job?.job_id,
    has_email: !!context?.email,
  }));

  if (!context || !context.job) {
    console.log('greenhouse: no context or job — exiting');
    return exit();
  }

  const profile = context; // profile fields are spread directly onto context by background.js

  // ── Form detection ─────────────────────────────────────────────────────────
  const form =
    document.querySelector('#application_form') ||
    document.querySelector('form[action*="greenhouse"]') ||
    document.querySelector('form[id*="application"]');

  console.log('greenhouse: form —', form ? (form.id || form.action || 'found') : 'not found');

  if (!form) {
    send({ type: 'needs_review', reason: 'not_a_standard_greenhouse_form' });
    return exit();
  }

  // ── Resume upload ──────────────────────────────────────────────────────────
  async function uploadResume() {
    const resumeInput =
      form.querySelector('input[type="file"][id*="resume" i]') ||
      form.querySelector('input[type="file"][name*="resume" i]') ||
      form.querySelector('input[type="file"]');

    if (!resumeInput) {
      console.log('greenhouse: resume input not found');
      send({ type: 'failed', reason: 'resume_pdf_unavailable' });
      return false;
    }

    console.log('greenhouse: fetching resume PDF');
    const blob = await new Promise(resolve => {
      chrome.runtime.sendMessage(
        { type: 'fetch_resume', job_id: context.job.job_id, job_ats: context.job.job_ats },
        response => {
          if (chrome.runtime.lastError || !response?.ok || !response.data) return resolve(null);
          const binary = atob(response.data);
          const bytes = new Uint8Array(binary.length);
          for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
          resolve(new Blob([bytes], { type: 'application/pdf' }));
        }
      );
    });

    if (!blob) {
      send({ type: 'failed', reason: 'resume_pdf_unavailable' });
      return false;
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
        if (confirmed || elapsed >= 3000) { clearInterval(poll); resolve(); }
      }, 200);
    });

    console.log('greenhouse: resume upload complete');
    return true;
  }

  // ── ATS config for filler_utils ────────────────────────────────────────────
  // Greenhouse wraps each question in a div.field or fieldset.
  // Labels the shared loop should skip — these are handled by the loop itself
  // via classification, but we skip file inputs and already-confirmed-working
  // edge cases that need special handling outside the loop.
  const atsConfig = {
    form,
    stabilityTimeoutMs: 3000,
    findSubmitButton: () =>
      form.querySelector('button[type="submit"]') ||
      form.querySelector('input[type="submit"]') ||
      document.querySelector('#submit_app'),
    detectSuccess: () => {
      const successText = /thank you|application received|successfully submitted/i;
      const urlChanged = !location.href.includes('/application');
      return successText.test(document.body.textContent) || urlChanged;
    },
  };

  // ── Fill all fields ────────────────────────────────────────────────────────
  await humanDelay(1000, 2000);

  // Resume first — some forms reveal additional fields after upload
  const resumeOk = await uploadResume();
  if (!resumeOk) return exit();

  await humanDelay(500, 1000);

  // Run the shared filler loop (multi-pass with DOM stability detection)
  await runFillerLoop(profile, context, atsConfig);

  // ── Submit or hand off ─────────────────────────────────────────────────────
  await humanDelay(1000, 2000);

  console.log('greenhouse: auto_submit —', context.auto_submit);

  if (!context.auto_submit) {
    send({ type: 'needs_review', reason: 'awaiting_user_submit' });
    // Stay alive: the form is filled and parked for the human to review and
    // click Submit themselves on this same page. Rather than polling
    // detectSuccess() blindly from the start (which can false-positive before
    // any click — e.g. detectSuccess's URL check has no baseline to compare
    // against yet), wait for the actual click on the submit button, THEN poll
    // for confirmation exactly like the auto-submit path does below.
    console.log('greenhouse: awaiting user submit — watching for click');
    const REVIEW_WAIT_MS = 30 * 60 * 1000; // matches background.js REVIEW_TIMEOUT_MS
    const submitBtn = atsConfig.findSubmitButton();

    if (submitBtn) {
      const clicked = await new Promise(resolve => {
        const timer = setTimeout(() => resolve(false), REVIEW_WAIT_MS);
        submitBtn.addEventListener('click', () => {
          clearTimeout(timer);
          resolve(true);
        }, { once: true });
      });

      if (clicked) {
        console.log('greenhouse: user clicked submit — waiting for confirmation');
        const confirmed = await waitFor(atsConfig.detectSuccess, 10000);
        if (confirmed) {
          console.log('greenhouse: submission confirmed');
          send({ type: 'success' });
        }
        // Ambiguous (clicked but no confirmation): leave it to the user —
        // don't send failed/released out from under a submit they just made.
        // The 30-min review timeout is the backstop if something's truly stuck.
      }
      // Not clicked within the window: say nothing: background.js's own
      // review timeout (same duration) will release the claim.
    } else {
      console.log('greenhouse: submit button not found — nothing to watch');
    }
    return exit();
  }

  const submitBtn = atsConfig.findSubmitButton();
  console.log('greenhouse: submit button —', submitBtn ? 'found' : 'not found');

  if (!submitBtn) {
    send({ type: 'failed', reason: 'submit_button_not_found' });
    return exit();
  }

  await clickElement(submitBtn);
  console.log('greenhouse: submit clicked — waiting for confirmation');

  const confirmed = await waitFor(atsConfig.detectSuccess, 10000);
  console.log('greenhouse: confirmation —', confirmed);

  if (confirmed) {
    send({ type: 'success' });
  } else {
    send({ type: 'failed', reason: 'submit_timeout' });
  }

  exit();
})();
