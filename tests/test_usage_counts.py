"""Lifetime / 7-day token + Tavily rollups from agent_runs."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_API = Path(__file__).resolve().parents[1] / "src" / "api"
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))

from usage_counts import compute_usage_summary  # noqa: E402


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE agent_runs (
            id INTEGER PRIMARY KEY,
            agent TEXT,
            finished_at TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            tavily_calls INTEGER,
            tavily_credits_est INTEGER,
            tavily_search_calls INTEGER,
            tavily_extract_calls INTEGER
        )
        """
    )
    conn.executemany(
        """
        INSERT INTO agent_runs (
            agent, finished_at, prompt_tokens, completion_tokens, total_tokens,
            tavily_calls, tavily_credits_est, tavily_search_calls, tavily_extract_calls
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            ("Dana", "2026-10-07T10:00:00+08:00", 100, 40, 140, 4, 6, 3, 1),
            ("Rex", "2026-09-01T10:00:00+08:00", 50, 10, 60, 2, 2, 2, 0),
            ("Dana", "2026-10-06T09:00:00+08:00", 20, 5, 25, 1, 2, 1, 0),
        ],
    )
    conn.commit()
    return conn


def test_usage_summary_splits_week_and_agent() -> None:
    conn = _db()
    out = compute_usage_summary(conn, "2026-10-01T00:00:00+08:00")
    assert out.lifetime.runs == 3
    assert out.lifetime.total_tokens == 225
    assert out.lifetime.tavily_credits_est == 10
    assert out.lifetime.tavily_search_calls == 6
    assert out.week.runs == 2
    assert out.week.total_tokens == 165
    assert out.week.tavily_credits_est == 8
    by = {row.agent: row for row in out.by_agent}
    assert by["Dana"].runs == 2
    assert by["Dana"].total_tokens == 165
    assert by["Rex"].tavily_calls == 2


def test_usage_summary_missing_table_is_zero() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    out = compute_usage_summary(conn, "2026-10-01T00:00:00+08:00")
    assert out.lifetime.runs == 0
    assert out.week.total_tokens == 0
    assert out.by_agent == []
