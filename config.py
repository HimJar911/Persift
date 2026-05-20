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
# Search profile — single place to configure what jobs to look for.
# Change these lists to target different roles (e.g. data science interns,
# new-grad SWE, etc.).
# ---------------------------------------------------------------------------

SEARCH_PROFILE = {
    "role_keywords": [
        "intern", "internship",
        "co-op", "coop",
        "apprentice", "apprenticeship",
    ],
    "domain_keywords": [
        # Core SWE
        "software", "engineer", "developer", "swe", "sde", "programming",
        # Web / stack
        "backend", "back end", "back-end",
        "frontend", "front end", "front-end",
        "fullstack", "full stack", "full-stack",
        # Infra / ops
        "devops", "dev ops", "sre", "site reliability",
        "cloud", "infrastructure", "platform",
        "embedded", "systems",
        # AI / ML
        "ai", "ml", "research",
        # Test
        "sdet",
    ],
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
