"""Telegram job-update payload helpers (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

_API = Path(__file__).resolve().parents[1] / "src" / "api"
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))

from telegram_notifier import _dashboard_button, _escape_md, send_job_update  # noqa: E402


def test_escape_md_covers_pipe_and_dot() -> None:
    assert "\\|" in _escape_md("a | b")
    assert "\\." in _escape_md("1.2")


def test_localhost_dashboard_button_is_omitted(monkeypatch) -> None:
    monkeypatch.delenv("DASHBOARD_PUBLIC_URL", raising=False)
    assert _dashboard_button() is None
    monkeypatch.setenv("DASHBOARD_PUBLIC_URL", "http://localhost:5173")
    assert _dashboard_button() is None
    monkeypatch.setenv("DASHBOARD_PUBLIC_URL", "https://example.com/dash")
    markup = _dashboard_button()
    assert markup is not None
    assert markup["inline_keyboard"][0][0]["url"] == "https://example.com/dash"


def test_escape_md_covers_pipe_and_dot() -> None:
    assert "\\|" in _escape_md("a | b")
    assert "\\." in _escape_md("1.2")


def test_send_job_update_skips_when_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert send_job_update("Rex", "New job stored", company="Acme", title="Eng") is False
