"""Profile basics.languages must accept LanguageItem dicts from CV/MCP."""

from __future__ import annotations

import sys
from pathlib import Path

_API = Path(__file__).resolve().parents[1] / "src" / "api"
if str(_API) not in sys.path:
    sys.path.insert(0, str(_API))

from models import Profile


def test_basics_languages_coerces_name_proficiency_dicts() -> None:
    profile = Profile.model_validate(
        {
            "basics": {
                "name": "Lychee",
                "languages": [
                    {"name": "Cantonese", "proficiency": "Native or bilingual proficiency"},
                    {"name": "English", "proficiency": "Professional working proficiency"},
                    {"name": "Putonghua", "proficiency": "Professional proficiency"},
                ],
            },
            "languages": [],
        }
    )
    assert profile.basics.languages == [
        "Cantonese (Native or bilingual proficiency)",
        "English (Professional working proficiency)",
        "Putonghua (Professional proficiency)",
    ]
    assert all(isinstance(item, str) for item in profile.basics.languages)


def test_top_level_languages_accept_chip_strings() -> None:
    profile = Profile.model_validate(
        {
            "basics": {"name": "Pat", "languages": ["Cantonese (Native)"]},
            "languages": ["Cantonese (Native)", {"name": "English", "proficiency": "Fluent"}],
        }
    )
    assert profile.languages[0].name == "Cantonese"
    assert profile.languages[1].name == "English"
