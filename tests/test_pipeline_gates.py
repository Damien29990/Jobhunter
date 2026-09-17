"""Tests for pipeline continuation after Rex."""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATORS = Path(__file__).resolve().parents[1] / "src" / "validators"
if str(_VALIDATORS) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS))

from pipeline_gates import (
    passes_dana_composite_gate,
    should_continue_after_rex,
    should_continue_after_dana,
)


def test_dana_requires_composite_not_transfer_bypass() -> None:
    assert passes_dana_composite_gate(80, 80) is True
    assert passes_dana_composite_gate(79, 80) is False
    assert passes_dana_composite_gate(50, 80) is False


def test_new_jobs_continue() -> None:
    assert should_continue_after_rex(3, 0) is True


def test_existing_high_score_queue_continues() -> None:
    assert should_continue_after_rex(0, 2) is True


def test_empty_scan_and_empty_queue_stops() -> None:
    assert should_continue_after_rex(0, 0) is False


def test_dana_continues_on_existing_proceed() -> None:
    assert should_continue_after_dana(0, 1) is True
    assert should_continue_after_dana(0, 0) is False
