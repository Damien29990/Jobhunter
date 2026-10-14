"""Pre-Rex listing sweep skips the hidden shelf and expires empty URLs."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_AGENTS = _ROOT / "src" / "agents"
_API = _ROOT / "src" / "api"
for extra in (_AGENTS, _API):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from listing_sweep import sweep_kanban_listings  # noqa: E402
from telegram_notifier import send_listing_sweep  # noqa: E402


def test_send_listing_sweep_skips_when_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert send_listing_sweep(checked=3, expired=1, items=[{"id": 1, "title": "A"}]) is False


def test_sweep_expires_visible_empty_url_skips_shelf(tmp_path, monkeypatch) -> None:
    db = tmp_path / "job_agent.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE job_postings (
            id INTEGER PRIMARY KEY,
            job_url TEXT,
            job_title TEXT,
            company_name TEXT,
            match_score INTEGER,
            expired INTEGER,
            user_status TEXT,
            application_status TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO job_postings VALUES (?,?,?,?,?,?,?,?)",
        [
            (1, "", "Visible dead", "Acme", 80, 0, None, None),
            (2, "https://example.com/job", "Hidden low", "Acme", 10, 0, None, None),
            (3, "", "Hidden uncon", "Acme", 90, 0, "UNCONSIDERABLE", None),
            (4, "", "Already expired", "Acme", 80, 1, None, None),
            (5, "", "Applied empty url", "Acme", 90, 0, None, "APPLIED"),
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr("listing_sweep._notify_sweep", lambda summary: None)
    summary = sweep_kanban_listings(db)
    assert summary["checked"] == 1
    assert summary["expired"] == 1
    assert summary["items"][0]["id"] == 1
    conn = sqlite3.connect(str(db))
    flags = {row[0]: row[1] for row in conn.execute("SELECT id, expired FROM job_postings")}
    conn.close()
    assert flags[1] == 1
    assert flags[2] == 0
    assert flags[3] == 0
    assert flags[5] == 0
