import os
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "10"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "")

# ---------------------------------------------------------------------------
# Search profile — exclude_keywords still gates is_intern_role (pollers/
# filter.py), the drop-gate used only by Workday and the Jobright cycle
# (main.py) — both deliberately out of scope for the ingestion-filter
# redesign that removed is_intern_role from the other 6 pollers. Do not
# widen this back into a general role/domain filter; role_keywords and
# domain_keywords (used only by the since-deleted matches_title()) were
# removed as dead code once that function's only caller turned out not to
# exist.
# ---------------------------------------------------------------------------

SEARCH_PROFILE = {
    "exclude_keywords": [
        "senior", "sr.", "sr ",
        "staff", "principal",
        "manager", "director",
        "lead", "vp", "head of",
        "distinguished", "fellow", "phd",
        # Non-SWE engineering disciplines that match "engineer"
        "supply chain", "manufacturing", "mechanical",
        "hardware", "marketing", "finance",
        "sales", "legal", "recruiting",
        "design systems", "data science",
        "ios", "android", "mobile",
    ],
}

# ---------------------------------------------------------------------------
# Fallback company slugs — used only if dynamic discovery fails
# ---------------------------------------------------------------------------

ASHBY_FALLBACK_SLUGS = [
    # AI / LLM
    "openai", "anthropic", "mistral", "cohere", "perplexity", "groq",
    "together-ai", "modal", "replicate", "weights-biases", "huggingface",
    "stability-ai", "character-ai", "inflection", "adept", "imbue",
    # Biotech / drug discovery
    "kensho", "genesis-therapeutics", "recursion", "insitro",
    # Aerospace / defense
    "shield-ai", "joby", "archer", "wisk", "overair", "beta-technologies",
    "hermeus", "varda", "relativity-space", "astranis", "albedo",
    "muon-space", "slingshot-aerospace", "axiom-space", "sierra-space",
    "vast", "epirus", "andromeda", "saildrone", "true-anomaly", "apex",
    "ursa-major", "firehawk", "launching-people", "skydio",
    # Robotics
    "sarcos", "sanctuary-ai", "1x-technologies", "apptronik",
    "agility-robotics", "figure", "physical-intelligence", "covariant",
    "intrinsic", "machina-labs",
    # Manufacturing
    "velo3d", "divergent", "hadrian",
    # Defense / gov tech
    "anduril", "palantir", "scale", "primer",
    # AI platforms / MLOps
    "c3ai", "dataiku", "domino-data-lab", "tecton", "arize", "fiddler",
    "arthur", "evidently", "aporia", "superwise", "truera", "whylabs",
    "mona", "censius", "deepchecks", "kolena", "aquarium",
    # Data labeling
    "labelbox", "snorkel", "diffgram", "encord", "segments", "hasty",
    "roboflow", "basicai", "appen", "lionbridge", "tasq", "surge",
    "remotasks",
    # Cloud / infra
    "cloudflare", "vercel", "netlify", "railway", "render", "fly-io",
    "supabase", "planetscale", "neon", "turso", "xata", "fauna",
    "upstash", "convex", "ditto", "electric-sql", "triplit", "jazz",
    "replicache", "powersync", "watermelondb", "rxdb", "vlcn",
    "cr-sqlite", "libsql", "rqlite", "dqlite", "litestream", "litefs",
    "marmot",
]

GREENHOUSE_FALLBACK_SLUGS = [
    "notion", "figma", "stripe", "airbnb", "robinhood", "brex", "rippling",
    "benchling", "scale-ai", "verkada", "plaid", "lattice", "retool",
    "airtable", "carta", "checkr", "coalition", "coda", "confluent",
    "coursera", "datadog", "discord", "doordash", "dropbox", "duolingo",
    "etsy", "fastly", "github", "grammarly", "greenhouse", "gusto",
    "hashicorp", "hubspot", "instacart", "intercom", "ivanti", "jellyfish",
    "khan-academy", "klaviyo", "lob", "looker", "lyft", "mapbox",
    "matterport", "mixpanel", "mongodb", "mozilla", "netlify", "okta",
    "opendoor", "pagerduty", "palantir", "persona", "postman", "quora",
    "ramp", "redfin", "reddit", "rubrik", "salesforce", "segment",
    "sendgrid", "sentry", "shopify", "slack", "smartsheet", "snyk",
    "sourcegraph", "squarespace", "sumo-logic", "superhuman", "tableau",
    "talkdesk", "thumbtack", "ticketmaster", "tiktok", "toast", "twilio",
    "twitch", "twitter", "typeform", "udemy", "vanta", "veeva", "verkada",
    "visa", "vivid-seats", "wayfair", "webflow", "weights-and-biases",
    "workato", "workiva", "yelp", "zapier", "zendesk", "zillow", "zoom",
    "zscaler",
]

LEVER_FALLBACK_SLUGS = [
    "netflix", "coinbase", "figma", "openai", "anthropic", "scale",
    "anduril", "nuro", "waymo", "cruise", "aurora", "zoox", "rivian",
    "lucid", "joby-aviation", "archer-aviation", "samsara", "toast",
    "dutchie", "faire", "fleet", "gem", "gladly", "gong", "grafana",
    "hasura", "heap", "highspot", "ironclad", "jumpcloud", "lacework",
    "launchdarkly", "lob", "logdna", "lucidchart", "lyra-health",
    "mentimeter", "mercury", "mindtickle", "modern-health", "motive",
    "narvar", "netlify", "newfront", "nexthink", "noom", "orca-security",
    "outreach", "patreon", "persona", "postman", "productboard",
    "proofpoint", "qualified", "quinstreet", "reachdesk", "recharge",
    "recurly", "redfin", "relay", "remote", "riskified", "rootly",
    "salesloft", "seismic", "sendoso", "shipbob", "sigma", "snyk",
    "sourcegraph", "sprinklr", "square", "squarespace", "sumo-logic",
    "superhuman", "swoogo", "sync", "talkdesk", "teachable", "teamwork",
    "terminus", "thrasio", "tidemark", "tipalti", "toast", "tonal",
    "tradedesk", "transfix", "tripactions", "truepill", "tuft-and-needle",
    "tuition-io", "twilio", "udemy", "uipath", "unbabel", "unqork",
    "upstart", "vanta", "verifone", "verizon", "vessel", "vida-health",
    "vise", "vroom", "watershed", "whoop", "wiz", "workato", "workiva",
    "yotpo", "zapier", "zendesk", "zeta", "zipline", "zoom", "zscaler",
]

SMARTRECRUITERS_FALLBACK_SLUGS = [
    "amazon", "visa", "mcdonalds", "deloitte", "bosch",
    "lidl", "aldi", "adidas", "bmw", "siemens",
    "continental", "zalando", "delivery-hero", "trivago",
    "scout24", "auto1", "hellofresh", "n26", "trade-republic",
    "celonis", "personio", "messagebird", "sumup", "solarisbank",
]

# ---------------------------------------------------------------------------
# Runtime tuning
# ---------------------------------------------------------------------------

OPENAI_MODEL = "gpt-4o"
OPENAI_MAX_TOKENS = 4096
LIBREOFFICE_TIMEOUT = 60
WORKDAY_SEARCH_TEXT = "intern"

# ML Model versions — format: "{model_name}-v{iteration}"
# Increment iteration when swapping models (e.g. Claude API, new sentence transformer).
# All new model_predictions rows are tagged with these at prediction time.
SCORER_MODEL_VERSION = "all-MiniLM-L6-v2-v1"
REWRITER_MODEL_VERSION = "gpt-4o-v1"
PIPELINE_VERSION = "1.0.0"
