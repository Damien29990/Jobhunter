"""System One gates for Rex evaluate and Dana re-research."""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATORS = Path(__file__).resolve().parents[1] / "src" / "validators"
if str(_VALIDATORS) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS))

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from system_one import should_evaluate_jd, should_rerun_dossier

HK = ZoneInfo("Asia/Hong_Kong")


def test_user_paste_always_evaluates() -> None:
    decision = should_evaluate_jd(
        title="x",
        content="short",
        user_supplied=True,
    )
    assert decision.proceed is True


def test_skips_already_scored_and_thin_jd() -> None:
    assert should_evaluate_jd(
        title="Engineer",
        content="x" * 200,
        already_scored=True,
    ).proceed is False
    assert should_evaluate_jd(
        title="Software Engineer Hong Kong",
        content="too short",
        url="https://hk.jobsdb.com/job/1",
    ).proceed is False


def test_evaluates_hk_it_vacancy() -> None:
    jd = (
        "We are hiring a Python backend engineer in Hong Kong "
        "for an IoT telemetry platform. FastAPI, PostgreSQL, on-site Kowloon."
    )
    decision = should_evaluate_jd(
        title="Python Backend Engineer",
        content=jd,
        url="https://hk.jobsdb.com/job/94495079",
    )
    assert decision.proceed is True


def test_dana_force_and_missing_dossier() -> None:
    assert should_rerun_dossier(has_dossier=False).proceed is True
    assert should_rerun_dossier(has_dossier=True, force=True).proceed is True


def test_dana_skips_fresh_confident_dossier() -> None:
    now = datetime.now(HK)
    decision = should_rerun_dossier(
        has_dossier=True,
        dossier_updated_at=now.isoformat(),
        dossier_confidence=80,
        newest_job_created_at=(now - timedelta(days=1)).isoformat(),
        force=False,
    )
    assert decision.proceed is False


def test_dana_reruns_when_newer_job_arrives() -> None:
    decision = should_rerun_dossier(
        has_dossier=True,
        dossier_updated_at="2026-09-20T12:00:00+08:00",
        dossier_confidence=80,
        newest_job_created_at="2026-09-22T10:00:00+08:00",
        force=False,
    )
    assert decision.proceed is True
