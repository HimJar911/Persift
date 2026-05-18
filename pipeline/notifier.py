import logging
import time
from pathlib import Path

import httpx

from config import SLACK_WEBHOOK_URL

logger = logging.getLogger(__name__)

# Module-level reusable client — created once, shared across notifications
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=15)
    return _client


def _format_posted_at(posted_at: int) -> str:
    """Return a human-readable relative time string for a ms-epoch timestamp."""
    if not posted_at:
        return "just now"
    delta_s = int(time.time()) - posted_at // 1000
    if delta_s < 60:
        return "just now"
    if delta_s < 3600:
        m = delta_s // 60
        return f"{m} minute{'s' if m != 1 else ''} ago"
    if delta_s < 86400:
        h = delta_s // 3600
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = delta_s // 86400
    return f"{d} day{'s' if d != 1 else ''} ago"


def _build_blocks(job: dict, changes: str, pdf_path: Path) -> list[dict]:
    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"\U0001f195 New {'Internship' if job.get('experience_level') != 'newgrad' else 'New Grad'} Alert",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Company:* {job['company_name']}"},
                {"type": "mrkdwn", "text": f"*Role:* {job['title']}"},
                {"type": "mrkdwn", "text": f"*Location:* {job['location']}"},
                {"type": "mrkdwn", "text": f"*ATS:* {job['ats'].title()}"},
                {"type": "mrkdwn", "text": f"*Posted:* {_format_posted_at(job.get('posted_at', 0))}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Work Model:* {job.get('work_model', 'Unknown')}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Categories:* {', '.join(job.get('categories', [])) or 'uncategorized'}",
                },
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Apply here:* <{job['apply_url']}|Open Application>",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Resume Changes:*\n{changes}",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Resume PDF saved to `{pdf_path.name}`",
                }
            ],
        },
    ]


async def send_slack_notification(job: dict, changes: str, pdf_path: Path) -> None:
    if not SLACK_WEBHOOK_URL or SLACK_WEBHOOK_URL == "your_webhook_here":
        logger.warning("Slack webhook not configured — skipping notification")
        return

    blocks = _build_blocks(job, changes, pdf_path)
    payload = {"blocks": blocks}

    client = _get_client()
    try:
        resp = await client.post(SLACK_WEBHOOK_URL, json=payload)
        resp.raise_for_status()
        logger.info(
            "Slack notification sent for %s at %s",
            job["title"],
            job["company_name"],
        )
    except httpx.HTTPError as exc:
        logger.error("Failed to send Slack notification: %s", exc)
