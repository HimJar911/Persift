-- migrations/022_seniority_classification.sql
-- Ingestion-filter redesign: pollers used to drop every job whose title
-- didn't match a narrow intern-only keyword regex (is_intern_role) before
-- it ever reached `jobs` — confirmed live (Jul 21 diagnostic) to silently
-- destroy ~99% of real postings at Greenhouse alone. Persift's actual scope
-- is every seniority level, not just interns, so ingestion keeps every job.
--
-- REVISED (same day, superseding the first version of this file applied
-- earlier): the first cut of this migration added a categorical
-- seniority_level enum (intern/new_grad/entry_level/mid_level/senior_level/
-- executive/not_applicable/unknown) classified by an LLM. Real ground truth
-- killed that design before it shipped: SmartRecruiters' own
-- employer-declared experienceLevel on 124 real "Director"-titled jobs
-- split 50% executive / 24% mid_level / 24% entry-or-not-applicable — proof
-- that even a real employer's own label is genuinely ambiguous for this
-- class of title, and any model (or human) guessing a single bucket from
-- title/description alone would be confidently wrong on roughly half of
-- them. The founder's call: never guess. Only store what a posting
-- literally states.
--
-- So this table only ever holds an EXPLICIT years-of-experience statement
-- extracted verbatim from the job's own title or description (e.g. "5+
-- years of experience" -> min=5, max=NULL; "2-4 years" -> min=2, max=4).
-- No inference from tone, scope, responsibilities, or reporting structure.
-- A job whose posting never states a number gets NULL on both columns and
-- is simply not filtered on this axis by the matcher — matched instead on
-- everything else it does carry (category, location, work_model,
-- sponsorship, etc.). NULL here means "not stated," never "unknown, guess
-- something" — that's the entire point of the redesign.
--
-- jobs.experience_level (free text, only ever populated by the Jobright
-- poller) is untouched by this migration — out of scope for this pass.

ALTER TABLE jobs ADD COLUMN years_of_experience_min SMALLINT;
ALTER TABLE jobs ADD COLUMN years_of_experience_max SMALLINT;

-- Verbatim structured metadata from the source ATS (Greenhouse's per-company
-- metadata[] array, Ashby's department/employmentType/team, Lever's
-- categories/workplaceType, SmartRecruiters' experienceLevel/function/
-- department/typeOfEmployment) — captured regardless of whether it says
-- anything about years of experience, so nothing is lost if a future need
-- for it shows up; reprocessing can read from here instead of re-polling.
ALTER TABLE jobs ADD COLUMN raw_ats_metadata JSONB;

-- Matcher's read path: find jobs with a stated lower bound to compare
-- against a user's own years of experience.
CREATE INDEX idx_jobs_years_of_experience_min ON jobs (years_of_experience_min)
    WHERE years_of_experience_min IS NOT NULL;
