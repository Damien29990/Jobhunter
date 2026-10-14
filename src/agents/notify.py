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
    job_id: Optional[int] = None,
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
            job_id=job_id,
        )
        if not ok:
            from telegram_notifier import LAST_SEND_ERROR
            reason = LAST_SEND_ERROR or "unconfigured or API rejected"
            log_activity(agent_name, f"Telegram job notify skipped or failed: {reason}", level="WARN")
        return ok
    except Exception as exc:
        log_activity(agent_name, f"Telegram notify error: {exc}", level="WARN")
        return False


def notify_application_package(
    *,
    company: str = "",
    title: str = "",
    url: str = "",
    extra: str = "",
    cv_pdf_path: str = "",
    cover_letter_path: str = "",
    checklist_path: str = "",
    dossier_path: str = "",
) -> bool:
    """Send Clara's pack the same way as the dashboard Telegram buttons."""
    try:
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env")
        from telegram_notifier import send_job_documents, send_job_update
        send_job_update(
            "Clara",
            "Application pack",
            company=company,
            title=title,
            url=url,
            extra=extra,
        )
        result = send_job_documents(
            cv_pdf_path=cv_pdf_path,
            cover_letter_path=cover_letter_path,
            checklist_path=checklist_path,
            dossier_path=dossier_path,
            company=company,
            title=title,
        )
        if not result.get("configured"):
            log_activity("Clara", "Telegram pack skipped: bot not configured", level="WARN")
            return False
        log_activity(
            "Clara",
            f"Telegram pack sent={result.get('sent')} failed={result.get('failed')}",
        )
        return bool(result.get("sent"))
    except Exception as exc:
        log_activity("Clara", f"Telegram pack error: {exc}", level="WARN")
        return False


def notify_apply_overview() -> bool:
    """Ask the running API to send the Apply overview so button sessions live there."""
    try:
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env")
        import os

        import httpx

        base = (os.environ.get("JOBHUNTER_API_URL") or "http://127.0.0.1:8000").rstrip("/")
        response = httpx.post(f"{base}/api/telegram/apply-overview", timeout=20.0)
        if response.status_code == 200:
            log_activity("Clara", "Apply overview sent via hosting API")
            return True
        log_activity(
            "Clara",
            f"Apply overview API {response.status_code} — FastAPI must be hosting",
            level="WARN",
        )
    except Exception as exc:
        log_activity(
            "Clara",
            f"Apply overview needs a running API (◀️ / ▶️): {exc}",
            level="WARN",
        )
    try:
        from apply_overview import send_apply_overview

        result = send_apply_overview()
        if result.get("ok"):
            log_activity("Clara", "Apply overview sent directly (API inbox not hosting)")
            return True
        return False
    except Exception as exc:
        log_activity("Clara", f"Apply overview direct send failed: {exc}", level="WARN")
        return False
