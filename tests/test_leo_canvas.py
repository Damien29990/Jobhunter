"""Leo Canvas template catalog — deterministic pick, no LLM."""

from __future__ import annotations

import sys
from pathlib import Path

_AGENTS = Path(__file__).resolve().parents[1] / "src" / "agents"
if str(_AGENTS) not in sys.path:
    sys.path.insert(0, str(_AGENTS))

from cv_canvas import get_canvas_template, list_canvas_templates, pick_canvas_template


def test_canvas_catalog_has_classic_compact_technical() -> None:
    ids = {item.id for item in list_canvas_templates()}
    assert {"classic", "compact", "technical"} <= ids


def test_pick_one_page_uses_compact() -> None:
    chosen = pick_canvas_template(
        jd_text="Please submit a one-page CV.",
        job_title="Software Engineer",
    )
    assert chosen.id == "compact"


def test_pick_platform_uses_technical() -> None:
    chosen = pick_canvas_template(
        jd_text="We need a platform engineer for IIoT telemetry.",
        job_title="Platform Engineer",
    )
    assert chosen.id == "technical"


def test_forced_id_wins() -> None:
    chosen = pick_canvas_template(
        jd_text="Please submit a one-page CV.",
        job_title="Software Engineer",
        forced_id="classic",
    )
    assert chosen.id == "classic"


def test_unknown_id_falls_back_to_classic() -> None:
    chosen = get_canvas_template("not-a-real-layout")
    assert chosen.id == "classic"
    assert chosen.file.endswith(".j2")
