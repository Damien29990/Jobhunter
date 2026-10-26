"""Apply Clara follow-up status to SQLite — dashboard PATCH and Telegram inbox.

# Ref: PATCH /api/jobs/{id}/follow-up
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from application_followup import (
    APPLICATION_STATUSES,
    STATUS_EMPLOYER_UPDATE,
    TERMINAL_STATUSES,
    normalize_application_status,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "job_agent.db"

_JOB_DETAIL_SELECT = """
    SELECT id, company_name, job_title, application_status, job_url,
           match_score, hard_skill_match_score, transferability_score,
           matched_skills, missing_skills, transferable_strengths,
           location_mode, salary_range, recommendation_reason,
           career_advisory_note, application_note, employer_update_note,
           application_status_at, application_ready, cv_status
    FROM job_postings WHERE id = ?
"""


def job_detail_from_row(row: sqlite3.Row) -> dict:
    """One job row as a Telegram/API detail dict. # Ref: job_postings"""
    return {
        "id": int(row["id"]),
        "company_name": row["company_name"] or "",
        "job_title": row["job_title"] or "",
        "application_status": row["application_status"] or "READY",
        "job_url": row["job_url"] or "",
        "match_score": row["match_score"],
        "hard_skill_match_score": row["hard_skill_match_score"],
        "transferability_score": row["transferability_score"],
        "matched_skills": row["matched_skills"] or "",
        "missing_skills": row["missing_skills"] or "",
        "transferable_strengths": row["transferable_strengths"] or "",
        "location_mode": row["location_mode"] or "",
        "salary_range": row["salary_range"] or "",
        "recommendation_reason": row["recommendation_reason"] or "",
        "career_advisory_note": row["career_advisory_note"] or "",
        "application_note": row["application_note"] or "",
        "employer_update_note": row["employer_update_note"] or "",
        "application_status_at": row["application_status_at"] or "",
        "application_ready": bool(row["application_ready"])
        if row["application_ready"] is not None
        else False,
        "cv_status": row["cv_status"] or "",
    }


def apply_application_follow_up(
    job_id: int,
    *,
    application_status: Optional[str] = None,
    application_note: Optional[str] = None,
    employer_update_note: Optional[str] = None,
) -> dict:
    """Update follow-up columns. Raises ValueError if missing job or no fields.

    Returns {id, company_name, job_title, application_status, job_url}.
    """
    if not DB_PATH.is_file():
        raise ValueError("job_agent.db missing")
    now = datetime.now(timezone(timedelta(hours=8))).isoformat()
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM job_postings WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"job {job_id} not found")
        current = dict(row)
        next_status = current.get("application_status")
        if application_status is not None:
            next_status = normalize_application_status(application_status)
        employer_note = employer_update_note
        if employer_note is not None:
            employer_note = employer_note.strip()
            current_norm = normalize_application_status(str(next_status or ""))
            if application_status is None and current_norm not in TERMINAL_STATUSES:
                next_status = STATUS_EMPLOYER_UPDATE
        sets: list[str] = []
        params: list[object] = []
        if application_status is not None or (
            employer_note is not None and next_status != current.get("application_status")
        ):
            sets.append("application_status = ?")
            params.append(next_status)
            sets.append("application_status_at = ?")
            params.append(now)
        if application_note is not None:
            sets.append("application_note = ?")
            params.append(application_note.strip())
        if employer_note is not None:
            sets.append("employer_update_note = ?")
            params.append(employer_note)
            sets.append("employer_update_at = ?")
            params.append(now)
        if not sets:
            raise ValueError("no fields to update")
        params.append(job_id)
        conn.execute(
            f"UPDATE job_postings SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        conn.commit()
        row = conn.execute(_JOB_DETAIL_SELECT, (job_id,)).fetchone()
        return job_detail_from_row(row)
    finally:
        conn.close()


def list_clara_jobs(limit: int = 12) -> list[dict]:
    """Clara-stage jobs: pack ready or already in a follow-up status."""
    if not DB_PATH.is_file():
        return []
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, company_name, job_title, application_status, application_ready
            FROM job_postings
            WHERE COALESCE(application_ready, 0) = 1
               OR TRIM(COALESCE(application_status, '')) NOT IN ('', 'READY')
            ORDER BY COALESCE(application_status_at, created_at) DESC
            LIMIT ?
            """,
            (max(1, min(30, int(limit))),),
        ).fetchall()
        return [
            {
                "id": int(r["id"]),
                "company_name": r["company_name"] or "",
                "job_title": r["job_title"] or "",
                "application_status": r["application_status"] or "READY",
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_clara_job(job_id: int) -> Optional[dict]:
    if not DB_PATH.is_file():
        return None
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(_JOB_DETAIL_SELECT, (job_id,)).fetchone()
        if row is None:
            return None
        return job_detail_from_row(row)
    finally:
        conn.close()


def status_token_ok(raw: str) -> bool:
    text = str(raw or "").strip().upper().replace("-", "_").replace(" ", "_")
    return text in APPLICATION_STATUSES
