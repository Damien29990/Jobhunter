"""Kanban column classification used by Dana's job-id dropdown."""

from __future__ import annotations

import sys
from pathlib import Path

_API = Path(__file__).resolve().parents[1] / "src" / "api"
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))

from gates import DANA_JOB_SELECT_STAGES, kanban_column


def test_discovered_is_below_dana_gate_without_dossier() -> None:
    assert kanban_column(72, None, False, None) == "discovered"


def test_vetting_is_high_score_without_dossier() -> None:
    assert kanban_column(82, None, False, None) == "vetting"


def test_vetted_has_verdict_before_cv() -> None:
    assert kanban_column(82, None, False, "PROCEED") == "vetted"
    assert kanban_column(40, None, False, "AVOID") == "vetted"


def test_materials_and_applied_outrank_verdict() -> None:
    assert kanban_column(90, "MATERIALS_GENERATED", False, "PROCEED") == "materials"
    assert kanban_column(90, None, True, "PROCEED") == "applied"


def test_dana_dropdown_keeps_discovered_and_vetted_only() -> None:
    assert "discovered" in DANA_JOB_SELECT_STAGES
    assert "vetted" in DANA_JOB_SELECT_STAGES
    assert "vetting" not in DANA_JOB_SELECT_STAGES
    assert kanban_column(72, None, False, None) in DANA_JOB_SELECT_STAGES
    assert kanban_column(82, None, False, "PROCEED") in DANA_JOB_SELECT_STAGES
    assert kanban_column(82, None, False, None) not in DANA_JOB_SELECT_STAGES
