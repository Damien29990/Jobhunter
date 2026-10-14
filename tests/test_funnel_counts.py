"""Header funnel KPIs count kanban-visible jobs only."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_API = Path(__file__).resolve().parents[1] / "src" / "api"
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))

from funnel_counts import compute_funnel  # noqa: E402


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE job_postings (
            id INTEGER PRIMARY KEY,
            company_name TEXT,
            match_score INTEGER,
            expired INTEGER,
            user_status TEXT,
            cv_status TEXT,
            application_ready INTEGER
        );
        CREATE TABLE company_dossiers (
            company_name TEXT PRIMARY KEY,
            vetting_verdict TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO job_postings VALUES (?,?,?,?,?,?,?)",
        [
            (1, "LiveCo", 90, 0, None, "MATERIALS_GENERATED", 0),
            (2, "LiveCo", 82, 0, None, None, 0),
            (3, "DeadCo", 88, 1, None, "MATERIALS_GENERATED", 1),
            (4, "LowCo", 20, 0, None, None, 0),
            (5, "SkipCo", 91, 0, "UNCONSIDERABLE", None, 0),
            (6, "ReadyCo", 85, 0, None, "MATERIALS_GENERATED", 1),
        ],
    )
    conn.executemany(
        "INSERT INTO company_dossiers VALUES (?,?)",
        [
            ("LiveCo", "PROCEED"),
            ("DeadCo", "PROCEED"),
            ("SkipCo", "PROCEED"),
        ],
    )
    conn.commit()
    return conn


def test_funnel_ignores_expired_low_score_and_unconsiderable() -> None:
    conn = _db()
    stats = compute_funnel(conn)
    conn.close()
    # Active: 1, 2, 6 (not 3 expired, 4 low score, 5 unconsiderable)
    assert stats["found"] == 3
    assert stats["score_ge_80"] == 3
    # LiveCo x2 + not DeadCo/SkipCo
    assert stats["vetted_proceed"] == 2
    assert stats["cv_generated"] == 2
    assert stats["application_ready"] == 1
