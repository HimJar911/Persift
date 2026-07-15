// popup.js — reads chrome.storage.local on open, renders one of 5 states,
// and wires all interactive controls (toggle, user ID, action buttons).

(async function () {
  'use strict';

  const root = document.getElementById('root');

  // ── Storage helpers ───────────────────────────────────────────────────────

  function loadState() {
    return new Promise(resolve =>
      chrome.storage.local.get(
        ['phase', 'current_job', 'paused', 'auto_submit', 'pending_review', 'user_id'],
        resolve
      )
    );
  }

  function loadUserId() {
    return new Promise(resolve =>
      chrome.storage.local.get('user_id', ({ user_id }) => resolve(user_id || ''))
    );
  }

  // ── Company icon color ────────────────────────────────────────────────────

  const _ICON_COLORS = ['#5B8DD9', '#9B59B6', '#E67E22', '#1ABC9C', '#E74C3C', '#3498DB'];

  function iconColor(name) {
    let h = 0;
    for (const c of (name || '')) h = (h * 31 + c.charCodeAt(0)) & 0xffff;
    return _ICON_COLORS[h % _ICON_COLORS.length];
  }

  function iconLetter(name) {
    return name ? name.charAt(0).toUpperCase() : '?';
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // ── HTML shell ────────────────────────────────────────────────────────────

  function buildShell({ dot, dotClass, statusText, body, buttons, queueLabel, autoSubmit, amber }) {
    return `
      <div class="card${amber ? ' card--amber' : ''}">
        <div class="header">
          <span class="header__logo">Persift</span>
          <div class="header__status">
            <div class="status-dot status-dot--${dotClass}"></div>
            <span class="status-label status-label--${dotClass}">${statusText}</span>
          </div>
        </div>
        <div class="body">${body}</div>
        ${buttons ? `<div class="btn-area">${buttons}</div>` : ''}
        <div class="footer">
          <span class="footer__queue">${queueLabel}</span>
          <div class="footer__toggle-group">
            <span class="toggle-label">Auto-submit</span>
            <div class="toggle ${autoSubmit ? 'toggle--on' : 'toggle--off'}" id="as-toggle">
              <div class="toggle__thumb"></div>
            </div>
          </div>
        </div>
        <div class="userid-section">
          <div class="userid-label">User ID</div>
          <input class="userid-input" id="uid-input" type="text"
                 placeholder="paste your user id" spellcheck="false" autocomplete="off">
        </div>
      </div>`;
  }

  function companyBlock(job) {
    const name  = job?.company_name || 'Unknown Company';
    const title = job?.title        || 'Unknown Role';
    const bg    = iconColor(name);
    return { name, title, html: `
      <div class="company-row">
        <div class="company-icon" style="background:${bg}">${escapeHtml(iconLetter(name))}</div>
        <span class="company-name">${escapeHtml(name)}</span>
      </div>
      <div class="job-title">${escapeHtml(title)}</div>` };
  }

  // ── State 0 — no user ID ─────────────────────────────────────────────────

  function renderUnconfigured(q, as) {
    root.innerHTML = buildShell({
      dotClass: 'muted', statusText: 'Not configured',
      body: `
        <p class="prose-primary">Enter your user ID below to start.</p>
        <p class="prose-secondary">Find it in your Persift dashboard.</p>`,
      buttons: '',
      queueLabel: q, autoSubmit: as, amber: false,
    });
    bindCommon(as);
  }

  // ── State 1 — filling ────────────────────────────────────────────────────

  function renderFilling(job, q, as) {
    const { html } = companyBlock(job);
    root.innerHTML = buildShell({
      dotClass: 'green', statusText: 'Applying',
      body: `
        <div class="section-label">Now applying</div>
        ${html}
        <div class="fill-status">
          <span class="fill-status__dot">●</span> Filling form…
        </div>`,
      buttons: `<button class="btn btn--outline" id="skip-btn">Stop &amp; Skip</button>`,
      queueLabel: q, autoSubmit: as, amber: false,
    });
    document.getElementById('skip-btn').addEventListener('click', async () => {
      await chrome.runtime.sendMessage({ type: 'skip' });
      await render();
    });
    bindCommon(as);
  }

  // ── State 2 — paused ────────────────────────────────────────────────────

  function renderPaused(q, as) {
    root.innerHTML = buildShell({
      dotClass: 'muted', statusText: 'Paused',
      body: `
        <p class="prose-primary">Applying is paused.</p>
        <p class="prose-secondary">Resume to continue processing your queue.</p>`,
      buttons: `<button class="btn btn--solid" id="resume-btn">Resume</button>`,
      queueLabel: q, autoSubmit: as, amber: false,
    });
    document.getElementById('resume-btn').addEventListener('click', async () => {
      await chrome.runtime.sendMessage({ type: 'resume' });
      await render();
    });
    bindCommon(as);
  }

  // ── State 3 — idle ───────────────────────────────────────────────────────

  function renderIdle(q, as) {
    root.innerHTML = buildShell({
      dotClass: 'green', statusText: 'Running',
      body: `
        <p class="prose-primary">Watching for new jobs…</p>
        <p class="prose-secondary">Next check in a few minutes.</p>`,
      buttons: `<button class="btn btn--outline" id="pause-btn">Pause</button>`,
      queueLabel: q, autoSubmit: as, amber: false,
    });
    document.getElementById('pause-btn').addEventListener('click', async () => {
      await chrome.runtime.sendMessage({ type: 'pause' });
      await render();
    });
    bindCommon(as);
  }

  // ── State 4 — post-submit wait ───────────────────────────────────────────

  function renderWaiting(job, q, as) {
    const { html } = companyBlock(job);
    root.innerHTML = buildShell({
      dotClass: 'green', statusText: 'Running',
      body: `
        <div class="section-label">Last applied</div>
        ${html}
        <p class="helper-text">Waiting before next application…</p>`,
      buttons: `<button class="btn btn--outline" id="pause-btn">Pause</button>`,
      queueLabel: q, autoSubmit: as, amber: false,
    });
    document.getElementById('pause-btn').addEventListener('click', async () => {
      await chrome.runtime.sendMessage({ type: 'pause' });
      await render();
    });
    bindCommon(as);
  }

  // ── State 5 — pending review ─────────────────────────────────────────────

  const _REASON_LABELS = {
    not_a_standard_greenhouse_form: 'Non-standard application form',
    multiple_file_uploads:          'Multiple file uploads required',
    awaiting_user_submit:           'Filled — waiting for your submit',
    skipped_complex:                'Complex form — manual apply needed',
  };

  function renderPendingReview(pending, q, as) {
    const { html }   = companyBlock(pending);
    const reasonText = _REASON_LABELS[pending?.reason] || escapeHtml(pending?.reason || 'Unknown reason');
    const applyUrl   = pending?.apply_url || '';
    // The extension normally detects the human's own Submit click on the page
    // itself and reports it automatically. These buttons are the fallback for
    // when that tab/content-script is gone (closed, reloaded, discarded).
    const isFilledReview = pending?.reason === 'awaiting_user_submit';

    root.innerHTML = buildShell({
      dotClass: 'amber', statusText: 'Needs review',
      body: `
        <div class="section-label">Needs your attention</div>
        ${html}
        <div class="amber-card">
          <div class="amber-card__title">Manual action required</div>
          <div class="amber-card__body">${reasonText}</div>
        </div>`,
      buttons: `
        ${applyUrl ? `<button class="btn btn--solid" id="open-btn" style="margin-bottom:6px">Open Application</button>` : ''}
        ${isFilledReview ? `<button class="btn btn--solid" id="confirm-btn" style="margin-bottom:6px">I submitted it</button>` : ''}
        <button class="btn btn--outline" id="dismiss-btn">Give up</button>`,
      queueLabel: q, autoSubmit: as, amber: true,
    });

    if (applyUrl) {
      document.getElementById('open-btn').addEventListener('click', () => {
        chrome.tabs.create({ url: applyUrl });
      });
    }
    if (isFilledReview) {
      document.getElementById('confirm-btn').addEventListener('click', async (e) => {
        const btn = e.currentTarget;
        btn.disabled = true;
        btn.textContent = 'Confirming…';
        const resp = await chrome.runtime.sendMessage({ type: 'manual_submit_confirm' });
        if (resp && resp.ok === false) {
          btn.disabled = false;
          btn.textContent = 'Couldn’t confirm — try again';
          return;
        }
        await render();
      });
    }
    document.getElementById('dismiss-btn').addEventListener('click', async () => {
      await chrome.runtime.sendMessage({ type: 'clear_review' });
      await render();
    });
    bindCommon(as);
  }

  // ── Common bindings (toggle + user ID input) ──────────────────────────────

  function bindCommon(currentAutoSubmit) {
    // Auto-submit toggle
    document.getElementById('as-toggle').addEventListener('click', async () => {
      const next = !currentAutoSubmit;
      await chrome.storage.local.set({ auto_submit: next });
      await render();
    });

    // User ID input — pre-fill from storage, save on blur or Enter
    const input = document.getElementById('uid-input');
    loadUserId().then(id => { input.value = id; });

    async function saveUserId() {
      const val = input.value.trim();
      if (val) {
        await chrome.storage.local.set({ user_id: val });
        await render();
      }
    }
    input.addEventListener('blur', saveUserId);
    input.addEventListener('keydown', e => { if (e.key === 'Enter') saveUserId(); });
  }

  // ── Main render ───────────────────────────────────────────────────────────

  async function render() {
    const state = await loadState();
    const { phase, current_job, paused, auto_submit, pending_review, user_id } = state;
    const as = auto_submit || false;

    let queueCount = null;
    try { queueCount = await getQueueCount(); } catch { /* ignore */ }
    const q = queueCount !== null ? `${queueCount} in queue` : '— in queue';

    if (!user_id) {
      renderUnconfigured(q, as);
    } else if (phase === 'awaiting_review' && pending_review) {
      renderPendingReview(pending_review, q, as);
    } else if (phase === 'tab_open' || phase === 'filling') {
      renderFilling(current_job, q, as);
    } else if (phase === 'post_submit_wait') {
      renderWaiting(current_job, q, as);
    } else if (paused) {
      renderPaused(q, as);
    } else {
      renderIdle(q, as);
    }
  }

  await render();
})();
