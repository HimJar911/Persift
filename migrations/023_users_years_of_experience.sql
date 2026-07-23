-- migrations/023_users_years_of_experience.sql
-- Adds the user-side counterpart to jobs.years_of_experience_min/max
-- (migration 022). The matcher's old job-type hard filter compared
-- job.experience_level against application_settings.job_types — a field no
-- onboarding flow ever populated (confirmed empty in production). This
-- replaces that dead filter with a real numeric comparison: a job whose
-- posting explicitly states a minimum years-of-experience only matches
-- users whose own years_of_experience meets it. Column, not JSONB, per the
-- field-home rule (CLAUDE.md / migration 016) — the matcher reasons about
-- this fact directly.
--
-- Nullable: no onboarding UI captures this yet either, so every existing
-- user starts NULL. A job with a stated minimum but a NULL user value does
-- not get excluded — see pipeline/matcher.py's hard filter, "no data on
-- either side means don't filter" is the same honest-null principle as
-- migration 022, applied symmetrically to the user side.

ALTER TABLE users ADD COLUMN years_of_experience SMALLINT;
