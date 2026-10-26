"""Clara Telegram command parser (no Bot API)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_API = _ROOT / "src" / "api"
_VALIDATORS = _ROOT / "src" / "validators"
for extra in (_API, _VALIDATORS):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from telegram_inbox import (  # noqa: E402
    clear_rex_await,
    extract_http_url,
    handle_parsed,
    parse_clara_text,
    rex_await_active,
    set_rex_await,
    start_rex_ingest,
)
from telegram_job_detail import format_job_telegram_detail, parse_skill_list  # noqa: E402
from telegram_notifier import clara_status_keyboard  # noqa: E402


def test_parse_clara_list_and_status() -> None:
    assert parse_clara_text("/clara")["kind"] == "list"
    cmd = parse_clara_text("/clara 110 APPLIED")
    assert cmd["kind"] == "status"
    assert cmd["job_id"] == 110
    assert cmd["status"] == "APPLIED"
    show = parse_clara_text("clara 12")
    assert show["kind"] == "show" and show["job_id"] == 12
    note = parse_clara_text("/note 12 portal Workday")
    assert note["kind"] == "note" and "Workday" in note["note"]
    assert parse_clara_text("/help")["kind"] == "help"
    bad = parse_clara_text("/clara 12 nope")
    assert bad["kind"] == "show" and bad.get("error")


def test_parse_rex_url_and_await() -> None:
    assert parse_clara_text("/rex")["kind"] == "rex_await"
    cmd = parse_clara_text("/rex https://hk.jobsdb.com/job/94977988")
    assert cmd["kind"] == "rex_ingest"
    assert cmd["job_url"] == "https://hk.jobsdb.com/job/94977988"
    bot = parse_clara_text(
        "/Rex@JobhunterBot https://www.linkedin.com/jobs/view/4456078398 extra"
    )
    assert bot["kind"] == "rex_ingest"
    assert "4456078398" in bot["job_url"]
    assert extract_http_url("see https://hk.jobsdb.com/job/1).") == (
        "https://hk.jobsdb.com/job/1"
    )


def test_rex_await_window() -> None:
    clear_rex_await()
    assert rex_await_active() is False
    set_rex_await()
    assert rex_await_active() is True
    clear_rex_await()
    assert rex_await_active() is False


def test_start_rex_ingest_uses_runner(monkeypatch) -> None:
    import agent_runner

    class FakeRunner:
        def pipeline_status(self) -> dict:
            return {"state": "IDLE"}

        def start(self, key: str, req) -> dict:
            assert key == "rex"
            assert req.job_url == "https://hk.jobsdb.com/job/1"
            return {"ok": True, "pid": 99}

    monkeypatch.setattr(agent_runner, "runner", FakeRunner())
    text = start_rex_ingest("https://hk.jobsdb.com/job/1")
    assert "ingesting" in text.lower()
    assert "jobsdb" in text.lower()


def test_start_rex_ingest_blocks_when_pipeline_running(monkeypatch) -> None:
    import agent_runner

    class BusyRunner:
        def pipeline_status(self) -> dict:
            return {"state": "RUNNING"}

        def start(self, key: str, req) -> dict:
            raise AssertionError("must not start Rex while pipeline is running")

    monkeypatch.setattr(agent_runner, "runner", BusyRunner())
    text = start_rex_ingest("https://hk.jobsdb.com/job/1")
    assert "already running" in text.lower()


def test_job_detail_includes_matched_and_gaps() -> None:
    text = format_job_telegram_detail(
        {
            "id": 742,
            "company_name": "Acme Systems",
            "job_title": "Full Stack Engineer",
            "application_status": "READY",
            "match_score": 72,
            "hard_skill_match_score": 68,
            "transferability_score": 76,
            "matched_skills": ["Python", "React"],
            "missing_skills": ["BACnet", "Workday"],
            "suitable": False,
            "job_url": "https://hk.jobsdb.com/job/1",
        },
        heading="Rex — Pasted job stored",
    )
    assert "#742" in text
    assert "Status: 🟢 READY" in text
    assert "suitable=false" in text
    assert "Matched:" in text
    assert "Python" in text
    assert "Gaps:" in text
    assert "BACnet" in text
    assert parse_skill_list('["Python","React"]') == ["Python", "React"]


def test_status_update_reply_is_full_job_card(monkeypatch) -> None:
    detail = {
        "id": 742,
        "company_name": "Acme Systems",
        "job_title": "Full Stack Engineer",
        "application_status": "APPLIED",
        "application_status_at": "2026-10-23T14:00:00+08:00",
        "match_score": 72,
        "matched_skills": ["Python"],
        "missing_skills": ["Kubernetes"],
        "job_url": "https://hk.jobsdb.com/job/1",
    }
    monkeypatch.setattr(
        "telegram_inbox.apply_application_follow_up",
        lambda job_id, **kwargs: detail,
    )
    reply = handle_parsed({"kind": "status", "job_id": 742, "status": "APPLIED"})
    assert "Clara updated" in reply
    assert "#742" in reply
    assert "Status: ✅ APPLIED" in reply
    assert "Matched:" in reply
    assert "Gaps:" in reply
    assert "Kubernetes" in reply


def test_clara_callback_payload_fits_telegram() -> None:
    markup = clara_status_keyboard(12345)
    labels = [btn["text"] for row in markup["inline_keyboard"] for btn in row]
    assert "✅ Applied" in labels
    assert "🟡 Await" in labels
    assert "🔴 Reject" in labels
    for row in markup["inline_keyboard"]:
        for btn in row:
            data = btn.get("callback_data") or ""
            if data:
                assert len(data.encode("utf-8")) <= 64
                assert data.startswith("c:12345:")
