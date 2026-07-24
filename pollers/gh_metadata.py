"""Parse Greenhouse's employer-configurable `metadata[]` array into a small,
normalized set of fields.

Greenhouse's `metadata` is NOT a platform-standard schema — it's whatever
custom questions each employer's Greenhouse admin configured, so the same
concept shows up under many different field *names* (confirmed via a live
census of every tracked company's postings, Jul 23 2026: 429 distinct
names total, but ~380 of them used by exactly one company — e.g. "BAYADA
Office address", "Neuralink Job Code" — internal HR-system exports that
don't generalize). Only field names confirmed to recur across 2+ companies,
AND whose real observed values are actually consistent with what the name
implies, are handled here.

Two names were found and deliberately excluded because their real values
contradicted the name: 'Job Type' (values are Regular/Standard/Pipeline/
Evergreen — a requisition workflow status, not employment type) and
'Work Type' (one company's values mix Full-time with Hybrid/Remote —
conflates employment-type and workplace-type under one field).

Every value here comes from *some* employer's free-typed config — treat
absence/None as "not stated," never guess a fallback.
"""

_EMPLOYMENT_TYPE_NAMES = frozenset({
    "Employment Type", "Employment type", "Employment Status",
    "Full-time/ Part-time", "Full Time/Part Time", "Full/Part Time",
    "Worker Type",
})

_WORKPLACE_TYPE_NAMES = frozenset({
    "Remote", "Remote?", "Workplace Type", "Work Arrangement",
    "Work Mode", "Work Model",
})

_EXPERIENCE_LEVEL_NAMES = frozenset({
    "Experience Level", "Experience level", "Experience Type",
    "Job Level", "Career Level", "Seniority Level",
})

_SALARY_RANGE_NAMES = frozenset({
    "Salary", "Salary Range", "Salary Range_Pay Transparency",
    "Job Posting Salary Range", "Pay Range",
})

_CATEGORY_METADATA_NAMES = frozenset({
    "Job Category", "Category", "Job Family", "Job Family Group",
    "Function", "Job Function", "Career Page Posting Category",
})


def _first_value(metadata: list[dict], names: frozenset[str]):
    """Return the first metadata entry's raw value whose name is in *names*,
    or None. Skips entries whose value is the literal string "null" (a real
    value Greenhouse's export uses for "not answered", confirmed in live
    data — distinct from a missing key or Python None) or an empty string.
    """
    for entry in metadata or []:
        if entry.get("name") in names:
            value = entry.get("value")
            if value is None or value == "null" or value == "":
                continue
            return value
    return None


def _clean_salary_range(raw) -> dict | None:
    """Return {unit, min_value, max_value} if raw looks like a real posted
    range, None otherwise. Filters the placeholder shape Greenhouse's own
    export uses for "field configured but not filled in" — confirmed live:
    both min_value and max_value are the string "0.0" in that case (not
    absent, not null — a literal zero-zero object), which is not a real
    $0 salary and must not be stored as one.
    """
    if not isinstance(raw, dict):
        return None
    min_v = raw.get("min_value")
    max_v = raw.get("max_value")
    if min_v in (None, "0.0") and max_v in (None, "0.0"):
        return None
    return {"unit": raw.get("unit"), "min_value": min_v, "max_value": max_v}


def parse_greenhouse_metadata(metadata: list[dict] | None) -> dict:
    """Extract the normalized core fields from a job's raw metadata array.

    Returns a dict with keys employment_type/workplace_type/experience_level/
    salary_range/category_metadata — any key whose value wasn't found (or
    only found as a placeholder) is None, same "honest null" rule as
    pollers/seniority.py.
    """
    if not metadata:
        return {
            "employment_type": None,
            "workplace_type": None,
            "experience_level": None,
            "salary_range": None,
            "category_metadata": None,
        }
    return {
        "employment_type": _first_value(metadata, _EMPLOYMENT_TYPE_NAMES),
        "workplace_type": _first_value(metadata, _WORKPLACE_TYPE_NAMES),
        "experience_level": _first_value(metadata, _EXPERIENCE_LEVEL_NAMES),
        "salary_range": _clean_salary_range(_first_value(metadata, _SALARY_RANGE_NAMES)),
        "category_metadata": _first_value(metadata, _CATEGORY_METADATA_NAMES),
    }
