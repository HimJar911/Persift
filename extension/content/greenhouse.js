console.log('greenhouse.js injected');

// Greenhouse application form filler.
// api.js and filler_utils.js are injected before this script — all utilities are globals.

(async function () {
  'use strict';

  // Relay every console.log to the service worker's console too — this
  // tab's own console output is lost the instant Greenhouse navigates to its
  // post-submit confirmation page, right when the log we care about most
  // (detectSuccess firing) would print. The service worker persists across
  // that navigation.
  const _origLog = console.log.bind(console);
  console.log = (...args) => {
    _origLog(...args);
    try {
      chrome.runtime.sendMessage({ type: 'debug_log', text: args.map(String).join(' ') });
    } catch { /* extension context may be gone */ }
  };

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
  // waitFor() (filler_utils.js) instead of a single immediate
  // querySelector() — a defensive improvement (give the DOM real time to
  // finish rendering, not just check once) kept even though it turned out
  // NOT to be the real cause of the not_a_standard_greenhouse_form spike
  // investigated Aug 7 2026 (~16-18% of real attempts, before AND after
  // this change — verified live, same rate both times). The actual root
  // cause was job_driver.py leaking old tabs across jobs, so THIS tab was
  // sometimes checking the wrong job's DOM entirely — see job_driver.py's
  // run_job() finally block for the real fix.
  const form = await waitFor(() =>
    document.querySelector('#application_form') ||
    document.querySelector('form[action*="greenhouse"]') ||
    document.querySelector('form[id*="application"]'),
    5000
  );

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
    // urlAtSubmit is stamped immediately before the submit click (both the
    // auto-submit and review-click paths below) so "success" means the URL
    // actually changed FROM that baseline — not an absolute substring test.
    // The old absolute check (!href.includes('/application')) was true from
    // page load on job-boards.greenhouse.io/* and boards.greenhouse.io/*/jobs/*
    // (neither ever contains "/application"), so detectSuccess() could return
    // true on the very first poll after a click that did nothing (validation
    // error, disabled button, network fail) — a fabricated applied_confirmed.
    urlAtSubmit: null,
    detectSuccess: () => {
      const successText = /thank you|application received|successfully submitted/i;
      const urlChanged = atsConfig.urlAtSubmit !== null && location.href !== atsConfig.urlAtSubmit;
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
    const reviewDeadline = Date.now() + REVIEW_WAIT_MS;

    // A click can be blocked client-side (e.g. a required field left empty)
    // with no navigation and no confirmation text — the user then fixes the
    // form and clicks again. A single { once: true } listener would already
    // be consumed by the first (failed) click and miss the real one, so this
    // loops: re-find the submit button and re-arm a fresh listener after
    // every non-confirmed click, until success or the review window expires.
    while (Date.now() < reviewDeadline) {
      const submitBtn = atsConfig.findSubmitButton();
      if (!submitBtn) {
        console.log('greenhouse: submit button not found — nothing to watch');
        break;
      }

      const clicked = await new Promise(resolve => {
        const timer = setTimeout(() => resolve(false), reviewDeadline - Date.now());
        submitBtn.addEventListener('click', () => {
          atsConfig.urlAtSubmit = location.href;
          clearTimeout(timer);
          resolve(true);
        }, { once: true });
      });

      if (!clicked) break; // review window expired without a click

      console.log('greenhouse: user clicked submit — waiting for confirmation');
      // This in-page poll only ever observes a same-page (SPA-style)
      // confirmation — if the click navigates the page instead, this whole
      // script's JS context (including this poll) is destroyed before it can
      // see the result. submit_clicked lets background.js catch that case
      // independently via tabs.onUpdated, which survives the navigation.
      send({ type: 'submit_clicked', url_at_submit: atsConfig.urlAtSubmit });
      const confirmed = await waitFor(atsConfig.detectSuccess, 10000);
      if (confirmed) {
        console.log('greenhouse: submission confirmed');
        send({ type: 'success' });
        break;
      }
      // Not confirmed: don't send failed/released out from under a submit
      // the user just made — loop back and re-arm for another attempt
      // (e.g. they still need to fix a validation error). If the click
      // actually navigated, background.js's independent check will resolve
      // this via pending_submission regardless of what happens here.
      console.log('greenhouse: click did not confirm — re-arming for another attempt');
    }
    return exit();
  }

  const submitBtn = atsConfig.findSubmitButton();
  console.log('greenhouse: submit button —', submitBtn ? 'found' : 'not found');

  if (!submitBtn) {
    send({ type: 'failed', reason: 'submit_button_not_found' });
    return exit();
  }

  atsConfig.urlAtSubmit = location.href;
  await clickElement(submitBtn);
  console.log('greenhouse: submit clicked — waiting for confirmation');
  // See the review-path comment above: this poll can only see a same-page
  // confirmation. A navigating submit destroys this script's context before
  // the poll's next tick, so background.js also tracks the click via
  // tabs.onUpdated and can resolve success independently of this result.
  send({ type: 'submit_clicked', url_at_submit: atsConfig.urlAtSubmit });

  const confirmed = await waitFor(atsConfig.detectSuccess, 10000);
  console.log('greenhouse: confirmation —', confirmed);

  if (confirmed) {
    send({ type: 'success' });
  } else {
    // Ambiguous, not necessarily failed: a navigating submit would also land
    // here (this poll can't see past the navigation). Don't report failed —
    // that would release a claim out from under a submission that may have
    // actually succeeded. background.js's pending_submission check is the
    // backstop; if the page truly didn't navigate and truly has no
    // confirmation text, the job simply stays in 'submitting' until the
    // server's lease-expiry sweep reclaims it.
    console.log('greenhouse: no in-page confirmation — deferring to background nav check');
  }

  exit();
})();
