# 0002 — `is_intern_role()` title-drop-gate removed from 5 pollers

**Date:** 2026-07-21
**Status:** accepted, live
**Files:** `pollers/greenhouse.py`, `ashby.py`, `lever.py`, `smartrecruiters.py`,
`custom.py`; `pollers/filter.py` (function definition kept, two callers remain)

## Context

`pollers/filter.py`'s `is_intern_role()` — a title-keyword drop gate called
inside all 6 direct-ATS pollers — was silently destroying **~99% of real
job postings** before they ever reached the `jobs` table. One Greenhouse
diagnostic: 56,940 real jobs seen, 593 survived the filter.

## Decision

Persift's actual scope is every seniority level, not just interns (founder
confirmed explicitly) — the filter was a leftover from an earlier, narrower
vision. Removed from `greenhouse.py`, `ashby.py`, `lever.py`,
`smartrecruiters.py`, `custom.py` — every job the ATS API returns now gets
inserted, no title-based filtering.

**`workday.py` and `main.py`'s Jobright cycle (`run_jobright_cycle`,
`run_seed`) still call `is_intern_role()` — deliberately, out of scope**
("Workday is a separate beast," "let's not worry about the jobright thing" —
founder's calls, not to be revisited without asking).

`pollers/filter.py` still defines `is_intern_role`/`_EXCLUDE_RE`/`_TOKEN_RE`/
`_ROLE_TOKENS` for those two remaining callers — do not delete.
`config.py`'s `SEARCH_PROFILE["exclude_keywords"]` kept for the same reason.

Dead code removed same session: `is_entry_level()` (zero callers),
`matches_title()` (claimed caller already deleted), `config.py`'s
`role_keywords`/`domain_keywords` (only used by the deleted `matches_title`).
