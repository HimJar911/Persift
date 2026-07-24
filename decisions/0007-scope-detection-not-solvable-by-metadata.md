# 0007 — Job scope-detection (in-scope vs. out-of-scope) cannot be solved by ATS metadata or company name

**Date:** 2026-07-23
**Status:** accepted (negative result) — no fix attempted, problem deliberately deferred
**Files:** `pollers/metadata_categories.py`

## Context

While building the department/function → category mapping (see STATE.md's
now-closed metadata-category work), SmartRecruiters' `function.label` values
`Other` and `General Business` turned out to be dominated by real
out-of-scope postings — Domino's delivery drivers, Groupement Mousquetaires
grocery-store roles, Greene King bar staff. This looked at first like it
might generalize: exclude retail-heavy employers, or exclude these two
ambiguous function labels, and out-of-scope noise goes away.

It doesn't. Checked systematically, not just on the first few examples.

## What was checked

**Company-level exclusion (e.g. "deactivate Domino's"):** Domino's
`Information Technology`-labeled jobs are real corporate HQ roles in Ann
Arbor, MI — Software Engineer III, Site Reliability Engineer, Director of
ML & AI, Architect IV — sitting in the same company record as 21,716
retail/delivery jobs. Company-level deactivation would discard real,
in-scope postings.

**Function-label exclusion (`Customer Service` / `Management`), checked
across every company using either label, not a sample:** genuinely mixed at
every level:

- ServiceNow (22 jobs under these labels): almost entirely real —
  VP Product Management, Senior Customer Success Manager, Staff Technical
  Support Engineer.
- LinkedIn (9 jobs): real — Account Executive, Director Labor Relations,
  Marketing Science Strategic Analyst.
- Arista Networks (3 jobs): real — Technical Solutions Engineer.
- CD PROJEKT RED (1 job): real — Senior Producer.
- WNS Global Services / Sutherland (202 / 188 jobs): overseas BPO
  call-center agents (South Africa, Philippines, Egypt, India) — genuinely
  out of scope.
- Harvard University (40 jobs): almost entirely out of scope — Kitchen
  Helper, Chiller Operator, Locksmith, Fire Mechanic, Laundry — but from a
  university, not a "retail employer."
- Deloitte (19 jobs): split within one company — legitimate director-level
  consulting roles alongside a genuine "Customer Care Lead" support role.
- Alphabe Insight Inc (377 jobs): mixed within itself — some plausible
  entry-level office roles (Project Coordinator, Communications Assistant)
  alongside what looks like MLM/door-to-door "marketing company" gig
  postings (Brand Representative – Event Marketing, Promotional Sales
  Assistant, Trade Show Staff, Event Staff).

No company name, function label, or department string reliably separates
"real in-scope job" from "out-of-scope job" — real professional roles and
real out-of-scope roles sit under the identical label, sometimes at the
identical employer.

## Decision

`Customer Service` and `Management` are excluded from
`_SMARTRECRUITERS_FUNCTION_MAP` entirely (return `None`, not a guess) — same
"honest null over a confident wrong answer" rule as
[0001](0001-seniority-classification-rejected.md). Title-based regex
classification (`pollers/filter.py`) already independently catches the real
professional titles in this set on its own; the metadata mapping doesn't
need to (and can't safely) add anything for these two labels specifically.

**This is not a scope-detection fix.** It only stops the metadata layer
from actively mislabeling jobs. It does not identify or exclude the WNS/
Sutherland/Harvard-style out-of-scope postings — those still get whatever
categories (or lack of one) the title-regex classifier already gives them,
which was already the status quo before this investigation.

## Open problem, not solved here

Reliable in-scope vs. out-of-scope detection at the individual-job level —
distinguishing a real professional role from a blue-collar/retail/BPO/
gig-adjacent posting — needs a different signal than company name, ATS
department/function metadata, or title regex. All three were checked and
each fails on real examples found in this session. Worth its own dedicated
investigation before attempting again; don't re-propose a company-level or
function-label-level exclusion list without new evidence it would generalize
better than what was checked here.
