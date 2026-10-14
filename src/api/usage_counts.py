"""Token and Tavily usage rollups from agent_runs.

# Ref: agent_runs — dashboard usage strip
"""

from __future__ import annotations

import sqlite3
from typing import Optional

try:
    from .models import AgentUsageByAgent, AgentUsageSummary, AgentUsageTotals
except ImportError:
    from models import AgentUsageByAgent, AgentUsageSummary, AgentUsageTotals


def empty_usage_totals() -> AgentUsageTotals:
    """Zeroed totals when the table is missing or empty.

    # Ref: agent_runs
    """
    return AgentUsageTotals()


def totals_from_row(row: Optional[sqlite3.Row]) -> AgentUsageTotals:
    """Map a SUM() row onto AgentUsageTotals.

    # Ref: agent_runs
    """
    if row is None:
        return empty_usage_totals()
    return AgentUsageTotals(
        runs=int(row["runs"] or 0),
        prompt_tokens=int(row["prompt_tokens"] or 0),
        completion_tokens=int(row["completion_tokens"] or 0),
        total_tokens=int(row["total_tokens"] or 0),
        tavily_calls=int(row["tavily_calls"] or 0),
        tavily_credits_est=int(row["tavily_credits_est"] or 0),
        tavily_search_calls=int(row["tavily_search_calls"] or 0),
        tavily_extract_calls=int(row["tavily_extract_calls"] or 0),
    )


USAGE_SUM_SQL = """
    SELECT
        COUNT(*) AS runs,
        COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
        COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
        COALESCE(SUM(total_tokens), 0) AS total_tokens,
        COALESCE(SUM(tavily_calls), 0) AS tavily_calls,
        COALESCE(SUM(tavily_credits_est), 0) AS tavily_credits_est,
        COALESCE(SUM(tavily_search_calls), 0) AS tavily_search_calls,
        COALESCE(SUM(tavily_extract_calls), 0) AS tavily_extract_calls
    FROM agent_runs
"""


def compute_usage_summary(conn: sqlite3.Connection, week_start: str) -> AgentUsageSummary:
    """Lifetime + last-7-days + per-agent totals.

    week_start is Asia/Hong_Kong ISO 8601. Missing table → zeros.

    # Ref: agent_runs
    """
    empty = AgentUsageSummary(lifetime=empty_usage_totals(), week=empty_usage_totals())
    try:
        life = conn.execute(USAGE_SUM_SQL).fetchone()
        week = conn.execute(
            USAGE_SUM_SQL + " WHERE finished_at >= ?",
            (week_start,),
        ).fetchone()
        by_rows = conn.execute(
            """
            SELECT agent,
                   COUNT(*) AS runs,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens,
                   COALESCE(SUM(tavily_calls), 0) AS tavily_calls,
                   COALESCE(SUM(tavily_credits_est), 0) AS tavily_credits_est
            FROM agent_runs
            GROUP BY agent
            ORDER BY total_tokens DESC, tavily_credits_est DESC
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return empty
    return AgentUsageSummary(
        lifetime=totals_from_row(life),
        week=totals_from_row(week),
        by_agent=[
            AgentUsageByAgent(
                agent=str(r["agent"] or ""),
                runs=int(r["runs"] or 0),
                total_tokens=int(r["total_tokens"] or 0),
                tavily_calls=int(r["tavily_calls"] or 0),
                tavily_credits_est=int(r["tavily_credits_est"] or 0),
            )
            for r in by_rows
        ],
    )
