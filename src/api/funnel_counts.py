"""Header funnel KPIs — counts match the main kanban (active jobs only).

# Ref: POST /api/stats/funnel · Header.jsx · _active_job_clause
"""

from __future__ import annotations

import sqlite3

try:
    from . import gates
except ImportError:
    import gates


def active_job_clause(alias: str = "") -> tuple[str, list]:
    """SQL: score ≥ 35, not expired, not unconsiderable.

    # Ref: gates.is_kanban_visible
    """
    prefix = f"{alias}." if alias else ""
    return (
        f"COALESCE({prefix}match_score, 0) >= ? AND COALESCE({prefix}expired, 0) = 0 "
        f"AND UPPER(COALESCE({prefix}user_status, '')) != ?",
        [gates.DASHBOARD_MIN_DISPLAY_SCORE, gates.USER_STATUS_UNCONSIDERABLE],
    )


def _count(conn: sqlite3.Connection, sql: str, params: tuple | list) -> int:
    row = conn.execute(sql, tuple(params)).fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def compute_funnel(conn: sqlite3.Connection) -> dict[str, int]:
    """Five header KPIs, each restricted to kanban-visible jobs.

    vetted_proceed is active jobs whose employer dossier is PROCEED (not a
    company count that includes expired listings).
    # Ref: FunnelStats / Header kpi.*
    """
    active_sql, active_params = active_job_clause()
    active_j, active_j_params = active_job_clause("j")
    found = _count(
        conn,
        f"SELECT COUNT(*) FROM job_postings WHERE {active_sql}",
        active_params,
    )
    score_ge_80 = _count(
        conn,
        f"SELECT COUNT(*) FROM job_postings WHERE {active_sql} AND match_score >= ?",
        list(active_params) + [gates.AGENT3_CV_MIN_SCORE],
    )
    vetted_proceed = _count(
        conn,
        "SELECT COUNT(*) FROM job_postings j "
        "JOIN company_dossiers d ON d.company_name = j.company_name "
        f"WHERE {active_j} AND UPPER(COALESCE(d.vetting_verdict, '')) = ?",
        list(active_j_params) + [gates.AGENT3_CV_REQUIRED_VERDICT],
    )
    cv_generated = _count(
        conn,
        f"SELECT COUNT(*) FROM job_postings WHERE {active_sql} "
        "AND cv_status IN ('MATERIALS_GENERATED', 'MATERIALS_RENDERED')",
        active_params,
    )
    application_ready = _count(
        conn,
        f"SELECT COUNT(*) FROM job_postings WHERE {active_sql} "
        "AND COALESCE(application_ready, 0) = 1",
        active_params,
    )
    return {
        "found": found,
        "score_ge_80": score_ge_80,
        "vetted_proceed": vetted_proceed,
        "cv_generated": cv_generated,
        "application_ready": application_ready,
    }
