"""Sweep kanban-visible job URLs before Rex searches.

Hidden shelf jobs (low score, already expired, unconsiderable) are skipped.
Dead listings are marked expired. One Telegram summary is sent.

# Ref: pipeline — before Rex; dashboard check_job / listing_check_verdict
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from typing import Optional

AGENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_DIR.parent.parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

_API_DIR = AGENT_DIR.parent / "api"
_VALIDATORS_DIR = AGENT_DIR.parent / "validators"
for extra in (_API_DIR, _VALIDATORS_DIR):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from activity_logger import log_activity, log_system  # noqa: E402
from listing_filters import (  # noqa: E402
    listing_check_verdict,
    listing_text_supports_title,
    listing_url_problem,
    normalize_listing_url,
)


def _fetch_page(url: str, timeout: float = 12.0) -> tuple[Optional[bool], Optional[int], str]:
    try:
        import httpx
    except ImportError:
        return None, None, "httpx missing"
    headers = {"User-Agent": "Mozilla/5.0 (Jobhunter listing sweep)"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            status = int(response.status_code)
            ok = status < 400 and status not in (404, 410)
            text = (response.text or "")[:80000] if ok else ""
            return ok, status, text
    except Exception as exc:
        return False, None, str(exc)[:200]


def sweep_kanban_listings(db_path: Optional[Path] = None) -> dict:
    """Check source links on the main kanban; expire dead ones; ping Telegram once.

    Returns {checked, expired, unknown, items: [{id, company, title, reason}]}.
    """
    from gates import is_kanban_visible

    path = Path(db_path or (PROJECT_ROOT / "job_agent.db"))
    summary: dict = {"checked": 0, "expired": 0, "unknown": 0, "items": []}
    if not path.is_file():
        return summary
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, job_url, job_title, company_name, match_score, expired, user_status "
            "FROM job_postings"
        ).fetchall()
        expired_items: list[dict] = []
        checked = 0
        unknown = 0
        for row in rows:
            if not is_kanban_visible(row["match_score"], row["expired"], row["user_status"]):
                continue
            checked += 1
            url = normalize_listing_url(str(row["job_url"] or "").strip())
            title = str(row["job_title"] or "")
            company = str(row["company_name"] or "")
            if not url:
                conn.execute("UPDATE job_postings SET expired = 1 WHERE id = ?", (row["id"],))
                expired_items.append(
                    {
                        "id": int(row["id"]),
                        "company": company,
                        "title": title,
                        "reason": "no job_url",
                    }
                )
                continue
            shape = listing_url_problem(url)
            if shape:
                still, expire, reason = listing_check_verdict(shape, None, None, None)
            else:
                http_ok, status, text = _fetch_page(url)
                title_found: Optional[bool] = None
                if http_ok:
                    title_found = listing_text_supports_title(text, title)
                still, expire, reason = listing_check_verdict(
                    None, http_ok, status, title_found
                )
                if http_ok is False and status is None:
                    reason = text or reason
            if expire:
                conn.execute("UPDATE job_postings SET expired = 1 WHERE id = ?", (row["id"],))
                expired_items.append(
                    {
                        "id": int(row["id"]),
                        "company": company,
                        "title": title,
                        "reason": reason,
                    }
                )
            elif not still:
                unknown += 1
        conn.commit()
        summary = {
            "checked": checked,
            "expired": len(expired_items),
            "unknown": unknown,
            "items": expired_items,
        }
    finally:
        conn.close()

    log_system(
        f"Listing sweep: checked={summary['checked']} expired={summary['expired']} "
        f"unknown={summary['unknown']}",
        level="INFO",
    )
    log_activity(
        "SYSTEM",
        f"Pre-Rex listing sweep: {summary['checked']} checked, "
        f"{summary['expired']} expired",
    )
    _notify_sweep(summary)
    return summary


def _notify_sweep(summary: dict) -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
        from telegram_notifier import send_listing_sweep

        send_listing_sweep(
            checked=int(summary.get("checked") or 0),
            expired=int(summary.get("expired") or 0),
            unknown=int(summary.get("unknown") or 0),
            items=list(summary.get("items") or []),
        )
    except Exception:
        return
