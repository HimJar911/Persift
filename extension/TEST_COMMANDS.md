# OfferUp Test

## 1. Update profile
```powershell
Get-Content .env | ForEach-Object { if ($_ -match '^([^=]+)=(.*)$') { [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2]) } }
python update_profile.py
```

## 2. Start API
```powershell
docker compose up -d
uvicorn api.server:app --reload
```

## 3. Reset job
```powershell
docker exec persift-db psql -U persift -d persift -c "UPDATE user_jobs SET status='applying', current_stage='applied', failure_reason='' WHERE job_id='8004171';"
```

**Verkada (active test):**
```powershell
docker exec persift-db psql -U persift -d persift -c "UPDATE user_jobs SET status='applying', failure_reason='' WHERE job_id='5099422007';"
```

## 4. Reload extension
`chrome://extensions` → Persift → reload icon

## 5. Service Worker console — reset state
```js
chrome.storage.local.set({phase:'idle', current_job:null, current_tab_id:null, phase_started_at:null, user_id:'46e66cfa-e625-4ffc-b8dc-7bf75e21db26'}, ()=>console.log('reset'))
```

## 6. Service Worker console — trigger poll
```js
runPollCycle()
```

Open DevTools on the new tab immediately to catch filler logs.

---

- URL: `https://job-boards.greenhouse.io/offerup/jobs/8004171`
- user_id: `46e66cfa-e625-4ffc-b8dc-7bf75e21db26`
