# Persift

Automated internship monitor — polls thousands of companies across 7 ATS platforms every 10 minutes, detects new postings, tailors your resume to each job using GPT-4o, and sends a Slack notification with the tailored PDF.

## What It Does

1. Discovers companies via Common Crawl CDX (Greenhouse, Lever, Ashby, Jobvite, SmartRecruiters)
2. Polls all discovered companies on a scheduled interval via their public APIs
3. Deduplicates against a local SQLite (or DynamoDB) seen-jobs store
4. Filters for intern/co-op/apprenticeship roles by keyword
5. Tailors your base resume to each job description via GPT-4o
6. Generates a PDF from the tailored `.docx`
7. Sends a Slack notification with job details, resume changes summary, and apply link

## How to Run

```bash
# First time: discover companies from Common Crawl, then seed the database
python discover_companies.py
python main.py --seed

# Normal operation: start live monitoring
python main.py

# Force fresh company discovery before starting
python main.py --discover
```

Run `--seed` once before your first live run to mark all currently-posted jobs as seen, so only genuinely new postings trigger notifications.

## Required `.env` Variables

```
OPENAI_API_KEY=sk-...
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
POLL_INTERVAL_MINUTES=10
LOG_LEVEL=INFO
DB_BACKEND=sqlite
AWS_REGION=us-east-1
DYNAMODB_TABLE=persift_seen_jobs
DYNAMODB_ENDPOINT=
```

Set `DB_BACKEND=dynamodb` to use AWS DynamoDB instead of local SQLite. Leave `DYNAMODB_ENDPOINT` blank for real AWS; set it to `http://localhost:8000` for DynamoDB Local.

## Resume Setup

Place your resume at `resume/base_resume.docx` (or `base_resume.pdf` — text is extracted automatically). Per-ATS formatting rules live in `resume/ats_prompts/`.
