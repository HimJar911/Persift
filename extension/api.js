// Shared API module — injected into content scripts and imported by background.js
// via importScripts('api.js'). All functions are globals; no ES module syntax.

const BASE_URL = 'http://localhost:8000';

async function getUserId() {
  const { user_id } = await chrome.storage.local.get('user_id');
  return user_id || null;
}

async function fetchNextJob() {
  const id = await getUserId();
  if (!id) return null;
  try {
    const resp = await fetch(`${BASE_URL}/jobs/queue?user_id=${encodeURIComponent(id)}&limit=1`);
    if (!resp.ok) return null;
    const data = await resp.json();
    return data.jobs?.[0] || null;
  } catch { return null; }
}

async function markApplied(jobId, jobAts) {
  const user_id = await getUserId();
  if (!user_id) return false;
  try {
    const resp = await fetch(`${BASE_URL}/jobs/${encodeURIComponent(jobId)}/applied`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id, job_ats: jobAts }),
    });
    return resp.ok;
  } catch { return false; }
}

async function markNeedsReview(jobId, jobAts, reason) {
  const user_id = await getUserId();
  if (!user_id) return false;
  try {
    const resp = await fetch(`${BASE_URL}/jobs/${encodeURIComponent(jobId)}/needs_review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id, job_ats: jobAts, reason }),
    });
    return resp.ok;
  } catch { return false; }
}

async function markFailed(jobId, jobAts, reason) {
  const user_id = await getUserId();
  if (!user_id) return false;
  try {
    const resp = await fetch(`${BASE_URL}/jobs/${encodeURIComponent(jobId)}/failed`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id, job_ats: jobAts, reason }),
    });
    return resp.ok;
  } catch { return false; }
}

async function getResumePdf(jobId, jobAts) {
  const user_id = await getUserId();
  if (!user_id) return null;
  try {
    const resp = await fetch(
      `${BASE_URL}/jobs/${encodeURIComponent(jobId)}/resume` +
      `?job_ats=${encodeURIComponent(jobAts)}&user_id=${encodeURIComponent(user_id)}`
    );
    if (!resp.ok) return null;
    return await resp.blob();
  } catch { return null; }
}

async function getProfile(userId) {
  try {
    const resp = await fetch(`${BASE_URL}/users/${encodeURIComponent(userId)}`);
    if (!resp.ok) return null;
    return await resp.json();
  } catch { return null; }
}

async function getQueueCount() {
  const user_id = await getUserId();
  if (!user_id) return null;
  try {
    const resp = await fetch(`${BASE_URL}/jobs/queue/count?user_id=${encodeURIComponent(user_id)}`);
    if (!resp.ok) return null;
    const data = await resp.json();
    return typeof data.count === 'number' ? data.count : null;
  } catch { return null; }
}
