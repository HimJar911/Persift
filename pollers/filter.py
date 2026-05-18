"""Keyword filter and category classifier for direct ATS pollers."""

import re
from config import SEARCH_PROFILE

# ---------------------------------------------------------------------------
# Seniority exclusion — blocks obvious senior/non-entry-level roles
# ---------------------------------------------------------------------------

def _compile_patterns(keywords: list[str]) -> re.Pattern:
    escaped = [re.escape(kw) for kw in keywords]
    return re.compile(r"\b(?:" + "|".join(escaped) + r")\b", re.IGNORECASE)

_EXCLUDE_RE = _compile_patterns(SEARCH_PROFILE["exclude_keywords"])

def is_entry_level(title: str) -> bool:
    """Return True if the title does not contain any seniority exclude keywords."""
    return not bool(_EXCLUDE_RE.search(title))


def is_intern_role(title: str) -> bool:
    """Return True if the title contains a role keyword (intern/co-op/etc.)
    and does not contain any seniority exclude keywords.

    Used by direct ATS pollers where the feed contains all job levels and
    we need to filter down to internship/apprenticeship postings only.
    """
    if _EXCLUDE_RE.search(title):
        return False
    tokens = _TOKEN_RE.findall(title.lower())
    return bool(_ROLE_TOKENS & set(tokens))


# ---------------------------------------------------------------------------
# Category classifier — assigns unified taxonomy categories to a job
# ---------------------------------------------------------------------------

_CATEGORY_PATTERNS: dict[str, re.Pattern] = {
    "software_engineering": _compile_patterns([
        "software engineer", "swe", "sde", "backend", "back end", "back-end",
        "frontend", "front end", "front-end", "fullstack", "full stack",
        "full-stack", "web developer", "ios developer", "android developer",
        "mobile developer", "platform engineer", "devops", "site reliability",
        "sre", "embedded", "firmware", "systems engineer",
    ]),
    "machine_learning_and_ai": _compile_patterns([
        "machine learning", "ml engineer", "ai engineer", "deep learning",
        "nlp", "llm", "computer vision", "data scientist", "research scientist",
        "applied scientist", "artificial intelligence", "generative ai",
    ]),
    "data_analysis": _compile_patterns([
        "data analyst", "business intelligence", "bi analyst",
        "analytics engineer", "data analytics", "reporting analyst",
    ]),
    "data_engineering": _compile_patterns([
        "data engineer", "data pipeline", "etl", "data infrastructure",
        "data platform",
    ]),
    "cybersecurity": _compile_patterns([
        "security engineer", "cybersecurity", "cyber security", "infosec",
        "penetration test", "devsecops", "security analyst", "soc analyst",
        "threat intelligence",
    ]),
    "product_management": _compile_patterns([
        "product manager", "product management", "pm intern", "associate pm",
        "apm", "technical product",
    ]),
    "business_analyst": _compile_patterns([
        "business analyst", "business analysis", "systems analyst",
        "process analyst", "operations analyst",
    ]),
    "consulting": _compile_patterns([
        "consultant", "consulting", "advisory", "strategy analyst",
        "management consulting",
    ]),
    "accounting_and_finance": _compile_patterns([
        "accountant", "accounting", "finance", "financial analyst",
        "investment banking", "equity research", "audit", "tax analyst",
        "treasury", "controller",
    ]),
    "marketing": _compile_patterns([
        "marketing", "growth", "demand generation", "brand", "content",
        "seo", "digital marketing", "social media", "campaign",
        "communications",
    ]),
    "sales": _compile_patterns([
        "sales", "account executive", "business development", "bdr", "sdr",
        "revenue", "account manager",
    ]),
    "creatives_and_design": _compile_patterns([
        "designer", "ux", "ui", "product design", "graphic design",
        "visual design", "motion design", "brand design", "illustrator",
    ]),
    "engineering_and_development": _compile_patterns([
        "hardware engineer", "electrical engineer", "mechanical engineer",
        "chemical engineer", "aerospace engineer", "civil engineer",
        "industrial engineer", "manufacturing engineer",
    ]),
    "human_resources": _compile_patterns([
        "human resources", "hr ", "recruiter", "recruiting", "talent",
        "people operations", "hris",
    ]),
    "legal_and_compliance": _compile_patterns([
        "legal", "compliance", "paralegal", "regulatory", "counsel",
        "attorney", "contracts",
    ]),
    "management_and_executive": _compile_patterns([
        "operations manager", "chief of staff", "strategy",
        "corporate development", "general manager",
    ]),
    "public_sector_and_government": _compile_patterns([
        "government", "public sector", "public policy", "federal",
        "defense", "intelligence", "civic",
    ]),
    "customer_service_and_support": _compile_patterns([
        "customer success", "customer support", "customer service",
        "client success", "technical support", "help desk",
    ]),
    "education_and_training": _compile_patterns([
        "education", "teaching", "curriculum", "instructional",
        "learning", "tutor", "training",
    ]),
    "health care": _compile_patterns([
        "health care", "clinical", "medical", "health", "biotech",
        "pharmaceutical", "nursing", "patient",
    ]),
    "supply_chain": _compile_patterns([
        "supply chain", "logistics", "procurement", "sourcing",
        "inventory", "warehouse", "operations", "fulfillment",
    ]),
    "arts_and_entertainment": _compile_patterns([
        "entertainment", "media", "film", "music", "gaming",
        "game developer", "animation", "production",
    ]),
    "project_management": _compile_patterns([
        "project manager", "program manager", "pmo", "scrum master",
        "agile", "project coordinator",
    ]),
}


def assign_categories(title: str, description: str = "") -> list[str]:
    """Return list of unified taxonomy categories matching this job.

    Matches against title + first 500 chars of description.
    Returns empty list if no categories match — job goes to 'other'.
    """
    text = f"{title} {description[:500]}"
    return [
        cat for cat, pattern in _CATEGORY_PATTERNS.items()
        if pattern.search(text)
    ]


# ---------------------------------------------------------------------------
# Legacy title filter — kept for backward compatibility (used by simplify.py)
# ---------------------------------------------------------------------------

_DOMAIN_RE = _compile_patterns(SEARCH_PROFILE["domain_keywords"])
_TOKEN_RE = re.compile(r"[a-z0-9\-]+")
_ROLE_TOKENS: frozenset[str] = frozenset({
    "intern", "interns", "internship", "internships",
    "co-op", "coop", "coops",
    "apprentice", "apprentices", "apprenticeship", "apprenticeships",
})


def matches_title(title: str) -> bool:
    """Return True if the job title looks like a role we care about.

    Must contain a ROLE keyword AND a DOMAIN keyword, and must NOT contain
    any EXCLUDE keyword.  Used by pollers/simplify.py.
    """
    if _EXCLUDE_RE.search(title):
        return False
    tokens = _TOKEN_RE.findall(title.lower())
    has_role = bool(_ROLE_TOKENS & set(tokens))
    return has_role and bool(_DOMAIN_RE.search(title))
