"""Tests for dashboard job-shelf buckets (low score / expired / unconsiderable)."""

from __future__ import annotations

import sys
from pathlib import Path

_API = Path(__file__).resolve().parents[1] / "src" / "api"
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))

from gates import shelf_bucket  # noqa: E402


def test_high_score_stays_on_kanban() -> None:
    assert shelf_bucket(80, False, None) is None
    assert shelf_bucket(35, False, "") is None


def test_low_score_goes_to_shelf() -> None:
    assert shelf_bucket(34, False, None) == "low_score"
    assert shelf_bucket(8, False, None) == "low_score"
    assert shelf_bucket(None, False, None) == "low_score"


def test_expired_beats_low_score() -> None:
    assert shelf_bucket(10, True, None) == "expired"
    assert shelf_bucket(90, True, None) == "expired"


def test_unconsiderable_beats_all() -> None:
    assert shelf_bucket(90, True, "UNCONSIDERABLE") == "unconsiderable"
    assert shelf_bucket(12, False, "unconsiderable") == "unconsiderable"
