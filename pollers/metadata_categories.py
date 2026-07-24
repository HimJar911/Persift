"""Map ATS-provided, employer-declared department/function metadata to
Persift's category taxonomy (see pollers/filter.py's _CATEGORY_PATTERNS for
the canonical 23-category list).

Every mapping here was built from a live, full-population census of every
company Persift currently tracks (Jul 23 2026) — SmartRecruiters'
function.label (35 distinct values, a closed platform enum), Ashby/Lever's
department (free text), Greenhouse's category_metadata (free text, only
26% of jobs have it at all). Real job titles inside each value were spot-
checked before mapping, not assumed from the label alone.

Only values with a clear, single-category real-world meaning are mapped.
Deliberately left unmapped (returns None), same "honest null beats a
guess" rule as pollers/seniority.py:
- SmartRecruiters 'Other' and 'General Business' — checked real titles:
  overwhelmingly retail/food-service/delivery/hospitality/trades roles
  (Domino's, Groupement Mousquetaires, Greene King, Equinox, etc.) that
  don't fit Persift's white-collar-early-career taxonomy at all, not an
  ambiguous case to force a guess on.
- SmartRecruiters 'Analyst', 'Science', 'Research', 'Administrative' —
  checked real titles: genuinely heterogeneous (Analyst alone spans lab
  technicians, financial analysts, network engineers, product analysts —
  no single category fits without misclassifying a real share of them).
- Ashby/Lever department values only mapped when they match this same
  short, confirmed-clean vocabulary — most department strings in the
  census were company-specific org names ('Woven City', 'SME & Growth
  Business') with no generalizable meaning.
"""

# SmartRecruiters function.label -> categories. Platform-enforced closed
# enum (confirmed live: 35 distinct values across all 387 tracked
# companies, 97.6% of jobs populated after the Jul 23 backfill).
#
# 'Customer Service' and 'Management' deliberately excluded — checked real
# postings under both labels across every company using them (not just a
# sample): both are genuinely mixed at every level, not just "mostly
# retail." Real in-scope senior/professional roles (ServiceNow's VP
# Product Management, LinkedIn's Account Executives, Arista Networks'
# Technical Solutions Engineers, CD PROJEKT RED's Senior Producer) sit
# under the exact same labels as real out-of-scope roles (Domino's
# Delivery Driver, Harvard University's Kitchen Helper/Chiller Operator/
# Locksmith, WNS/Sutherland's overseas BPO call-center agents) — even
# within one company (Deloitte: legitimate director-level consulting
# roles alongside a Customer Care Lead). No company-name or label-based
# rule reliably separates them. Mapping either way would be a guess, not
# an extraction — same rule as everywhere else in this module. Title-
# based regex classification (pollers/filter.py) already independently
# catches the real professional titles in this set; it doesn't need this
# mapping's help, and this mapping can't safely add anything beyond what
# regex already gets right for these two labels specifically.
_SMARTRECRUITERS_FUNCTION_MAP: dict[str, str] = {
    "Information Technology": "software_engineering",
    "Consulting": "consulting",
    "Health Care Provider": "health care",
    "Sales": "sales",
    "Business Development": "sales",
    "Marketing": "marketing",
    "Advertising": "marketing",
    "Public Relations": "marketing",
    "Writing/Editing": "marketing",
    "Human Resources": "human_resources",
    "Legal": "legal_and_compliance",
    "Finance": "accounting_and_finance",
    "Accounting/Auditing": "accounting_and_finance",
    "Supply Chain": "supply_chain",
    "Distribution": "supply_chain",
    "Purchasing": "supply_chain",
    "Project Management": "project_management",
    "Product Management": "product_management",
    "Education": "education_and_training",
    "Training": "education_and_training",
    "Strategy/Planning": "management_and_executive",
    "Manufacturing": "engineering_and_development",
    "Production": "engineering_and_development",
    "Quality Assurance": "engineering_and_development",
    "Engineering": "engineering_and_development",
    "Design": "creatives_and_design",
    "Art/Creative": "creatives_and_design",
}

# Ashby/Lever department values confirmed to match this vocabulary
# unambiguously in the live census. Case-insensitive lookup (both
# 'Engineering' and 'ENGINEERING' were observed for the same company type).
_DEPARTMENT_MAP: dict[str, str] = {
    "engineering": "software_engineering",
    "vehicle engineering": "engineering_and_development",
    "product": "product_management",
    "sales": "sales",
    "business development": "sales",
    "marketing": "marketing",
    "people & talent": "human_resources",
    "hr & employee experience": "human_resources",
    "legal & licensing": "legal_and_compliance",
    "legal": "legal_and_compliance",
    "compliance": "legal_and_compliance",
    "regulatory & compliance": "legal_and_compliance",
    "finance": "accounting_and_finance",
    "finance & corporate development": "accounting_and_finance",
    "design": "creatives_and_design",
    "creative": "creatives_and_design",
    "customer experience": "customer_service_and_support",
    "security": "cybersecurity",
}

# Greenhouse departments[].name values confirmed to match this vocabulary
# unambiguously in a live census (361/367 tracked companies, 41,442 jobs,
# Jul 23 2026) — only names whose real sampled job titles were consistent
# with the name were included. Names that looked clean but whose real
# titles turned out genuinely mixed (Technology, IT, Development, Data,
# R&D, Growth, Operations, Support, Corporate — spot-checked, e.g.
# 'Operations' included everything from Junior Product Manager to
# CareGiver to Robot Operator) were deliberately left out, same "honest
# null" rule as everywhere else in this module.
_GREENHOUSE_DEPARTMENT_MAP: dict[str, str] = {
    "engineering": "software_engineering",
    "software engineering": "software_engineering",
    "software": "software_engineering",
    "software development": "software_engineering",
    "hardware": "engineering_and_development",
    "hardware engineering": "engineering_and_development",
    "mechanical engineering": "engineering_and_development",
    "manufacturing": "engineering_and_development",
    "sales": "sales",
    "field sales": "sales",
    "enterprise sales": "sales",
    "business development": "sales",
    "sales development": "sales",
    "account management": "sales",
    "finance": "accounting_and_finance",
    "accounting": "accounting_and_finance",
    "marketing": "marketing",
    "paid media": "marketing",
    "product management": "product_management",
    "product": "product_management",
    "legal": "legal_and_compliance",
    "compliance": "legal_and_compliance",
    "human resources": "human_resources",
    "information technology": "software_engineering",
    "customer success": "customer_service_and_support",
    "customer support": "customer_service_and_support",
    "customer service": "customer_service_and_support",
    "supply chain": "supply_chain",
    "design": "creatives_and_design",
}


def map_smartrecruiters_function(function_label: str | None) -> str | None:
    """SmartRecruiters function.label -> one category, or None if unmapped."""
    if not function_label:
        return None
    return _SMARTRECRUITERS_FUNCTION_MAP.get(function_label)


def map_department(department: str | None) -> str | None:
    """Ashby/Lever department (free text) -> one category, or None if
    unmapped. Case-insensitive since the same real value appears in both
    Title Case and ALL CAPS across different companies.
    """
    if not department:
        return None
    return _DEPARTMENT_MAP.get(department.strip().lower())


def map_greenhouse_departments(departments: list[dict] | None) -> str | None:
    """Greenhouse departments[] (list of {name, ...}) -> one category, or
    None if unmapped. Returns the first entry whose name matches the known
    vocabulary; case-insensitive for the same reason as map_department.
    """
    if not departments:
        return None
    for entry in departments:
        name = entry.get("name")
        if name:
            mapped = _GREENHOUSE_DEPARTMENT_MAP.get(name.strip().lower())
            if mapped:
                return mapped
    return None
