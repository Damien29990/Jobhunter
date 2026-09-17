"""Thin Telegram helper for agent processes (Rex/Dana/Leo/Clara).

Agents live in src/agents; the Bot API client lives in src/api. This module
resolves that path and never raises — a failed ping must not crash a scan.

# Ref: notify on each job_postings / dossier / CV / checklist write
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from activity_logger import log_activity

_API_DIR = Path(__file__).resolve().parent.parent / "api"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_API_DIR) not in sys.path:
    sys.path.insert(0, str(_API_DIR))


def notify_job_update(
    agent_name: str,
    event: str,
    *,
    company: str = "",
    title: str = "",
    score: Optional[int] = None,
    url: str = "",
    extra: str = "",
) -> bool:
    """Send one Telegram message for a single job-row update."""
    try:
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env")
        from telegram_notifier import send_job_update
        ok = send_job_update(
            agent_name,
            event,
            company=company,
            title=title,
            score=score,
            url=url,
            extra=extra,
        )
        if not ok:
            from telegram_notifier import LAST_SEND_ERROR
            reason = LAST_SEND_ERROR or "unconfigured or API rejected"
            log_activity(agent_name, f"Telegram job notify skipped or failed: {reason}", level="WARN")
        return ok
    except Exception as exc:
        log_activity(agent_name, f"Telegram notify error: {exc}", level="WARN")
        return False
