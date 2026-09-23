"""CV project shortlist: 2-4 items, side projects last."""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATORS = Path(__file__).resolve().parents[1] / "src" / "validators"
if str(_VALIDATORS) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS))

from cv_projects import select_and_order_cv_projects


def test_caps_at_four_work_projects() -> None:
    projects = [
        {
            "name": f"Work {i}",
            "is_side_project": False,
            "tech_stack": ["Python"] if i < 4 else ["Excel"],
            "description": "pipeline",
        }
        for i in range(6)
    ]
    picked = select_and_order_cv_projects(projects, "Python backend pipeline")
    assert len(picked) == 4
    assert all(not item["is_side_project"] for item in picked)


def test_side_projects_come_last() -> None:
    projects = [
        {
            "name": "Side IoT",
            "is_side_project": True,
            "tech_stack": ["IoT", "MQTT"],
            "description": "sensor mesh",
        },
        {
            "name": "Work API",
            "is_side_project": False,
            "tech_stack": ["Python"],
            "description": "API",
        },
    ]
    picked = select_and_order_cv_projects(projects, "IoT MQTT sensor Python")
    assert [item["name"] for item in picked] == ["Work API", "Side IoT"]


def test_fills_with_related_side_when_few_work() -> None:
    projects = [
        {
            "name": "Work",
            "is_side_project": False,
            "tech_stack": ["Java"],
            "description": "legacy",
        },
        {
            "name": "Hobby game",
            "is_side_project": True,
            "tech_stack": ["Unity"],
            "description": "game",
        },
        {
            "name": "Side FastAPI",
            "is_side_project": True,
            "tech_stack": ["FastAPI", "PostgreSQL"],
            "description": "API",
        },
    ]
    picked = select_and_order_cv_projects(projects, "FastAPI PostgreSQL backend")
    names = [item["name"] for item in picked]
    assert names[0] == "Work"
    assert "Side FastAPI" in names
    assert names[-1] != "Work" or len(names) == 1
    assert not names.index("Work")  # work is first
    assert "Hobby game" not in names


def test_does_not_copy_unrelated_work_to_fill_four() -> None:
    projects = [
        {
            "name": "Related A",
            "is_side_project": False,
            "tech_stack": ["Python"],
            "description": "API",
        },
        {
            "name": "Related B",
            "is_side_project": False,
            "tech_stack": ["Python"],
            "description": "pipeline",
        },
        {
            "name": "Unrelated",
            "is_side_project": False,
            "tech_stack": ["Excel"],
            "description": "spreadsheet",
        },
        {
            "name": "Side IoT",
            "is_side_project": True,
            "tech_stack": ["Excel"],
            "description": "hobby",
        },
    ]
    picked = select_and_order_cv_projects(projects, "Python FastAPI pipeline")
    names = [item["name"] for item in picked]
    assert set(names) == {"Related A", "Related B"}
    assert "Unrelated" not in names
    assert "Side IoT" not in names
