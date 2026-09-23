"""CV download filename: {job_name}_{user_name}_cv.pdf."""

from __future__ import annotations

import sys
from pathlib import Path

_AGENTS = Path(__file__).resolve().parents[1] / "src" / "agents"
if str(_AGENTS) not in sys.path:
    sys.path.insert(0, str(_AGENTS))

from cv_filenames import cv_download_filename, filename_token


def test_cv_download_filename_pattern() -> None:
    name = cv_download_filename(
        "Technical Manager, Platforms Engineering",
        "Damien, YU Chung Hei",
        "pdf",
    )
    assert name == "Technical_Manager_Platforms_Engineering_Damien_YU_Chung_Hei_cv.pdf"


def test_filename_token_strips_windows_illegal() -> None:
    assert "/" not in filename_token("A/B:C*")
    assert filename_token("") == "file"


def test_typ_extension() -> None:
    assert cv_download_filename("Data Engineer", "Damien", "typ").endswith("_cv.typ")


def test_cover_letter_filename() -> None:
    from cv_filenames import cover_letter_filename

    name = cover_letter_filename("Full-Stack Engineer", "Damien YU", "pdf")
    assert name.endswith("_cover_letter.pdf")
    assert "Full-Stack" in name or "Full_Stack" in name
