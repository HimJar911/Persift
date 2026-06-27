# Extension Test Commands

Run these in order every time you want to test the Greenhouse end-to-end flow.

---

## 1. Terminal — start Docker + API

```bash
cd C:\Users\himan\Desktop\Persift\Persift
docker compose up -d
uvicorn api.server:app --reload
```

## 2. Terminal (new tab) — reset test job in DB

```bash
docker exec persift-db psql -U persift -d persift -c "UPDATE user_jobs SET status='applying', current_stage='applied', failure_reason='' WHERE job_id='5153686008';"
```

## 3. Chrome — reload the extension

Go to `chrome://extensions` → find Persift → click the reload icon (circular arrow).

## 4. Chrome — open Service Worker console

On the same `chrome://extensions` page → click **"service worker"** link under Persift → DevTools opens.

## 5. Service Worker console — reset extension state

```js
chrome.storage.local.set({phase:'idle', current_job:null, current_tab_id:null, phase_started_at:null, user_id:'46e66cfa-e625-4ffc-b8dc-7bf75e21db26'}, ()=>console.log('reset'))
```

## 6. Service Worker console — trigger poll

```js
runPollCycle()
```

A new tab opens with the Greenhouse job. **Immediately open DevTools on that tab** (right-click → Inspect) to catch the greenhouse.js logs.

---

## Test job details

- job_id: `5153686008`
- ATS: `greenhouse`
- URL: `https://job-boards.greenhouse.io/internshiplist2000/jobs/5153686008`
- user_id: `46e66cfa-e625-4ffc-b8dc-7bf75e21db26`
- email: `him@persift.com`

---

## Check custom_answers keys (Service Worker console)

```js
fetch('http://localhost:8000/users/46e66cfa-e625-4ffc-b8dc-7bf75e21db26').then(r=>r.json()).then(d=>d.custom_answers.forEach(a=>console.log(a.questionKey)))
```

## Check label HTML for unfilled field (Greenhouse tab console)

Replace `'text to find'` with part of the question label you want to inspect:

```js
Array.from(document.querySelectorAll('label')).find(l=>l.textContent.toLowerCase().includes('text to find'))?.closest('li,div[class*="field"],div[class*="question"]')?.outerHTML?.slice(0,600)
```

---

## Verify new code loaded (Service Worker console)

Run after every extension reload to confirm the latest greenhouse.js is active:

```js
fetch(chrome.runtime.getURL('content/greenhouse.js')).then(r=>r.text()).then(t=>console.log('loaded:',t.includes('handledLabels'),t.includes('__country-listbox'),!t.includes("getElementById('question_15354233008')")))
```

Expected output: `loaded: true true true`

---

## Kill service worker (force fresh reload)

If the extension seems to be running old code:
1. `chrome://extensions` → reload Persift
2. Click "service worker" → DevTools opens
3. Application tab → Service Workers → click Stop
4. Close DevTools window
5. Click "service worker" again to restart fresh
6. Run the verify command above before testing
