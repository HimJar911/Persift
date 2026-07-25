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
_TOKEN_RE = re.compile(r"[a-z0-9\-]+")
_ROLE_TOKENS: frozenset[str] = frozenset({
    "intern", "interns", "internship", "internships",
    "co-op", "coop", "coops",
    "apprentice", "apprentices", "apprenticeship", "apprenticeships",
})

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
        "consultant", "consulting", "advisory services", "strategy analyst",
        "management consulting", "strategy consultant",
    ]),
    "accounting_and_finance": _compile_patterns([
        "accountant", "accounting", "financial analyst",
        "investment banking", "equity research", "financial audit",
        "tax analyst", "treasury analyst", "corporate controller",
    ]),
    "marketing": _compile_patterns([
        "marketing", "demand generation", "brand marketing",
        "brand manager", "content marketing", "seo specialist",
        "digital marketing", "social media marketing",
        "social media manager", "marketing campaign",
        "communications specialist", "communications manager",
    ]),
    "sales": _compile_patterns([
        "sales representative", "sales associate", "sales executive",
        "sales development", "account executive", "business development",
        "bdr", "sdr", "revenue operations", "account manager",
    ]),
    "creatives_and_design": _compile_patterns([
        "designer", "ux design", "ui design", "ux/ui", "product design",
        "graphic design", "visual design", "motion design", "brand design",
        "illustrator",
    ]),
    "engineering_and_development": _compile_patterns([
        "hardware engineer", "electrical engineer", "mechanical engineer",
        "chemical engineer", "aerospace engineer", "civil engineer",
        "industrial engineer", "manufacturing engineer",
    ]),
    "human_resources": _compile_patterns([
        "human resources", "hr generalist", "hr manager", "hr business partner",
        "recruiter", "recruiting coordinator", "talent acquisition",
        "people operations", "hris",
    ]),
    "legal_and_compliance": _compile_patterns([
        "legal counsel", "legal associate", "legal analyst", "compliance officer",
        "compliance analyst", "compliance manager", "paralegal",
        "regulatory affairs", "regulatory compliance", "general counsel",
        "attorney", "contracts manager", "contracts specialist",
    ]),
    "management_and_executive": _compile_patterns([
        "operations manager", "chief of staff", "corporate strategy",
        "strategy manager", "corporate development", "general manager",
    ]),
    "public_sector_and_government": _compile_patterns([
        "government relations", "public sector", "public policy",
        "federal government", "defense contractor", "intelligence analyst",
        "civic engagement",
    ]),
    "customer_service_and_support": _compile_patterns([
        "customer success", "customer support", "customer service",
        "client success", "technical support", "help desk",
    ]),
    "education_and_training": _compile_patterns([
        "teaching", "curriculum design", "instructional design",
        "e-learning", "learning experience", "learning designer", "tutor",
        "training program", "training specialist", "training coordinator",
    ]),
    "health care": _compile_patterns([
        "health care", "healthcare", "clinical research", "clinical trial",
        "medical device", "medical affairs", "biotech", "pharmaceutical",
        "nursing", "patient care", "patient experience",
    ]),
    "supply_chain": _compile_patterns([
        "supply chain", "logistics", "procurement", "sourcing specialist",
        "inventory management", "warehouse operations", "fulfillment",
        "logistics operations", "fleet operations",
    ]),
    "arts_and_entertainment": _compile_patterns([
        "entertainment industry", "media production", "film production",
        "music industry", "gaming industry", "game developer", "animation",
        "video production", "content production", "broadcast",
    ]),
    "project_management": _compile_patterns([
        "project manager", "program manager", "pmo", "scrum master",
        "agile coach", "project coordinator",
    ]),
}


def assign_categories(title: str, description: str = "") -> list[str]:
    """Return list of unified taxonomy categories matching this job.

    Title-first: the title alone is checked before the description is
    consulted at all. Full-description matching pulls in unrelated
    boilerplate (benefits/EEO/perks sections) that shares vocabulary with
    the taxonomy — e.g. "contracts" in a legal disclaimer tagging an
    engineering role `legal_and_compliance`, or "medical" in a benefits
    blurb tagging a civil-engineer role `health care`. Real examples
    confirmed live: a nurse posting tagged `marketing`, a VP-SWE role
    tagged with 8 unrelated categories (see STATE.md, decisions/0003).
    Description is only searched if the title resolves nothing, to catch
    jobs whose title alone is uninformative (e.g. a generic "Associate").
    Returns empty list if nothing matches — job goes to 'other'.
    """
    title_matches = [
        cat for cat, pattern in _CATEGORY_PATTERNS.items()
        if pattern.search(title)
    ]
    if title_matches:
        return title_matches

    text = f"{title} {description}"
    return [
        cat for cat, pattern in _CATEGORY_PATTERNS.items()
        if pattern.search(text)
    ]
