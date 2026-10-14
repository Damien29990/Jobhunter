"""Persist one agent execution's token + Tavily usage into SQLite.

# Ref: agent_runs — dashboard per-run usage panel
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

from activity_logger import HK_TZ, PROJECT_ROOT
from datetime import datetime

DB_PATH = PROJECT_ROOT / "job_agent.db"

_DDL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    pipeline_id TEXT,
    started_at TEXT,
    finished_at TEXT,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    llm_calls INTEGER DEFAULT 0,
    tavily_calls INTEGER DEFAULT 0,
    tavily_credits_est INTEGER DEFAULT 0,
    tavily_search_calls INTEGER DEFAULT 0,
    tavily_extract_calls INTEGER DEFAULT 0
);
"""


def ensure_agent_runs_table(conn: sqlite3.Connection) -> None:
    conn.execute(_DDL)


def persist_agent_run(snap: dict[str, object], db_path: Optional[Path] = None) -> None:
    path = db_path or DB_PATH
    finished = datetime.now(HK_TZ).isoformat()
    pipeline_id = (os.environ.get("JOBHUNTER_PIPELINE_RUN_ID") or "").strip() or None
    started = (os.environ.get("JOBHUNTER_AGENT_RUN_STARTED") or "").strip() or None
    row = (
        str(snap.get("agent") or ""),
        pipeline_id,
        started or str(snap.get("started_at") or finished),
        finished,
        int(snap.get("prompt_tokens") or 0),
        int(snap.get("completion_tokens") or 0),
        int(snap.get("total_tokens") or 0),
        int(snap.get("llm_calls") or 0),
        int(snap.get("tavily_calls") or 0),
        int(snap.get("tavily_credits_est") or 0),
        int(snap.get("tavily_search_calls") or 0),
        int(snap.get("tavily_extract_calls") or 0),
    )
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        ensure_agent_runs_table(conn)
        conn.execute(
            """
            INSERT INTO agent_runs (
                agent, pipeline_id, started_at, finished_at,
                prompt_tokens, completion_tokens, total_tokens, llm_calls,
                tavily_calls, tavily_credits_est, tavily_search_calls,
                tavily_extract_calls
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )
        conn.commit()
    finally:
        conn.close()
