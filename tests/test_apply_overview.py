"""Apply overview session: prev/next wrap and 2-hour expiry."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_API = _ROOT / "src" / "api"
_VALIDATORS = _ROOT / "src" / "validators"
for extra in (_API, _VALIDATORS):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from apply_overview import (  # noqa: E402
    ApplySession,
    apply_job_keyboard,
    apply_list_keyboard,
    apply_nav_keyboard,
    list_job_button_label,
    list_page_count,
    list_status_label,
    page_count,
    page_kind,
    render_apply_page,
    session_expired,
    step_session,
)
from telegram_inbox import parse_clara_text  # noqa: E402


def _session(ids: list[int], index: int = 0) -> ApplySession:
    return ApplySession(
        id="k8f2c1ab",
        chat_id="1",
        created_at="2026-10-12T11:32:00+08:00",
        expires_at="2026-10-12T13:32:00+08:00",
        job_ids=ids,
        index=index,
    )


def test_prev_next_wrap_overview_and_jobs() -> None:
    session = _session([133, 287, 349], index=0)
    step_session(session, 1)
    assert session.index == 1
    step_session(session, 1)
    assert session.index == 2
    step_session(session, 1)
    assert session.index == 3
    step_session(session, 1)
    assert session.index == 0
    step_session(session, -1)
    assert session.index == 3


def test_nav_keyboard_is_prev_next_only() -> None:
    markup = apply_nav_keyboard("k8f2c1ab")
    row = markup["inline_keyboard"][0]
    assert [b["text"] for b in row] == ["◀️ Previous", "Next ▶️"]
    assert row[0]["callback_data"] == "a:k8f2c1ab:p"
    assert row[1]["callback_data"] == "a:k8f2c1ab:n"
    for btn in row:
        assert len(btn["callback_data"].encode("utf-8")) <= 64


def test_job_keyboard_has_url_and_actions() -> None:
    markup = apply_job_keyboard(
        "k8f2c1ab",
        {
            "id": 577,
            "job_url": "https://jobs.ctgoodjobs.hk/job/10283629",
            "cv_pdf_path": "",
            "cover_letter_pdf_path": "",
        },
    )
    labels = [btn["text"] for row in markup["inline_keyboard"] for btn in row]
    assert "🔗 View Job" in labels
    assert "✅ Mark Applied" in labels
    assert "📝 Edit Details" in labels
    assert "📋 List" in labels
    assert labels[-3:] == ["◀️ Previous", "📋 List", "Next ▶️"]
    view = markup["inline_keyboard"][0][0]
    assert view["url"] == "https://jobs.ctgoodjobs.hk/job/10283629"
    for row in markup["inline_keyboard"]:
        for btn in row:
            data = btn.get("callback_data") or ""
            if data:
                assert len(data.encode("utf-8")) <= 64


def test_session_expires_after_two_hours() -> None:
    session = _session([133])
    hk = timezone(timedelta(hours=8))
    assert not session_expired(session, datetime(2026, 10, 12, 13, 31, tzinfo=hk))
    assert session_expired(session, datetime(2026, 10, 12, 13, 32, tzinfo=hk))


def test_overview_lists_scores() -> None:
    session = _session([133], index=0)
    jobs = [
        {
            "id": 133,
            "company_name": "Axonex Intelligence Limited",
            "job_title": "Full Stack Web Developer",
            "match_score": 90,
            "application_status": "READY",
            "source_domain": "hk.jobsdb.com",
        }
    ]
    text = render_apply_page(session, jobs)
    assert "1 job found" in text
    assert "90/100" in text
    assert "Axonex" in text
    assert "💼 Full Stack Web Developer" in text
    assert "🏢 Axonex Intelligence Limited" in text
    assert "🟢 READY" in text
    detail = render_apply_page(step_session(session, 1), jobs)
    assert "📊 1/1" in detail
    assert "#133" in detail
    assert "Match: 90/100" in detail
    assert "💼 Full Stack Web Developer" in detail


def test_many_jobs_use_list_pages() -> None:
    ids = list(range(1, 21))
    session = _session(ids, index=0)
    assert list_page_count(20) == 3
    assert page_count(session) == 23
    assert page_kind(session) == ("list", 0)
    step_session(session, 1)
    assert page_kind(session) == ("list", 1)
    step_session(session, 1)
    assert page_kind(session) == ("list", 2)
    step_session(session, 1)
    assert page_kind(session) == ("card", 0)
    jobs = [
        {
            "id": i,
            "company_name": f"Co{i}",
            "job_title": f"Role {i}",
            "match_score": 80,
            "application_status": "READY",
        }
        for i in ids
    ]
    page0 = render_apply_page(_session(ids, index=0), jobs)
    assert "Page 1 of 3" in page0
    assert "Showing 1–8" in page0
    assert "20 jobs found" in page0
    assert "01 · `#1`" in page0
    page2 = render_apply_page(_session(ids, index=2), jobs)
    assert "Showing 17–20" in page2


def test_list_keyboard_opens_job_by_index() -> None:
    ids = [577, 133, 287]
    session = _session(ids, index=0)
    jobs = [
        {"id": 577, "match_score": 85, "job_title": "A", "company_name": "OnTheList"},
        {"id": 133, "match_score": 90, "job_title": "B", "company_name": "Axonex"},
        {"id": 287, "match_score": 89, "job_title": "C", "company_name": "AppicIDEA"},
    ]
    markup = apply_list_keyboard(session, jobs)
    labels = [btn["text"] for row in markup["inline_keyboard"] for btn in row]
    assert list_job_button_label(1, 85) == "01"
    assert list_status_label("APPLIED") == "✅ APPLIED"
    assert "01" in labels
    assert "02" in labels
    assert markup["inline_keyboard"][0] == [
        {"text": "01", "callback_data": "a:k8f2c1ab:j0"},
        {"text": "02", "callback_data": "a:k8f2c1ab:j1"},
        {"text": "03", "callback_data": "a:k8f2c1ab:j2"},
    ]
    nav = markup["inline_keyboard"][-1]
    assert [btn["text"] for btn in nav] == ["◀️ Previous", "Page 1/1", "Next ▶️"]
    page = render_apply_page(session, jobs)
    assert "💡 Tap a number to open the job" in page
    assert "01 · `#577`" in page
    assert "🏷️" not in page


def test_list_card_shows_location_and_tags() -> None:
    session = _session([539], index=0)
    jobs = [
        {
            "id": 539,
            "job_title": "AI Solutions Engineer",
            "company_name": "Robotics Panda Company Limited",
            "match_score": 90,
            "application_status": "APPLIED",
            "location_mode": "Hong Kong",
            "matched_skills": ["React", "Node.js", "AI-Native Workflow"],
        }
    ]
    page = render_apply_page(session, jobs)
    assert "📍 Hong Kong" in page
    assert "🏷️ React / Node.js / AI-Native Workflow" in page
    assert "✅ APPLIED" in page
    assert "🎯 90/100" in page


def test_parse_apply_command() -> None:
    assert parse_clara_text("/apply")["kind"] == "apply_overview"


def test_announce_pipeline_finish_writes_snapshot(tmp_path, monkeypatch) -> None:
    import apply_overview as ao

    snap_path = tmp_path / "pipeline_last_finish.json"
    monkeypatch.setattr(ao, "FINISH_SNAPSHOT_PATH", snap_path)
    monkeypatch.setattr(
        ao,
        "list_apply_jobs",
        lambda limit=12: [
            {
                "id": 42,
                "company_name": "Axonex Intelligence Limited",
                "job_title": "Full Stack Web Developer",
                "match_score": 90,
            }
        ],
    )
    monkeypatch.setattr(ao, "send_apply_overview", lambda: {"ok": True, "jobs": 1})
    snap = ao.announce_pipeline_finish(success=True, source="desk")
    assert snap.application_ready == 1
    assert snap.job_ids == [42]
    assert snap.telegram_ok is True
    loaded = ao.load_finish_snapshot()
    assert loaded is not None
    assert loaded.job_ids == [42]
    assert loaded.source == "desk"
