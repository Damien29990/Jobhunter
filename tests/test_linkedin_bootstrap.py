"""LinkedIn vanity username validation and fill-empty profile merge."""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATORS = Path(__file__).resolve().parents[1] / "src" / "validators"
_AGENTS = Path(__file__).resolve().parents[1] / "src" / "agents"
for extra in (_VALIDATORS, _AGENTS):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from contact_links import (
    is_valid_linkedin_username,
    name_from_linkedin_handle,
)
from linkedin_bootstrap import merge_fill_empty, merge_linkedin_mcp, skeleton_profile


def test_valid_username_and_url() -> None:
    assert is_valid_linkedin_username("damien-yu") is True
    assert is_valid_linkedin_username("@damien-yu") is True
    assert is_valid_linkedin_username("https://www.linkedin.com/in/damien-yu/") is True
    member = "ACoAADpA5CQBnR5PniLbi108ITQdzOXllP1ZfJ8"
    assert is_valid_linkedin_username(f"https://www.linkedin.com/in/?profileId={member}") is True
    assert is_valid_linkedin_username("https://lnkd.in/abcdEF12") is True


def test_rejects_company_pages_and_junk() -> None:
    assert is_valid_linkedin_username("https://www.linkedin.com/company/mtr") is False
    assert is_valid_linkedin_username("ab") is False
    assert is_valid_linkedin_username("not a handle") is False
    assert is_valid_linkedin_username("") is False


def test_name_from_slug() -> None:
    assert name_from_linkedin_handle("damien-yu") == "Damien Yu"


def test_skeleton_sets_linkedin_handle() -> None:
    profile = skeleton_profile("damien-yu", "https://www.linkedin.com/in/damien-yu")
    assert profile["basics"]["linkedin"] == "damien-yu"
    assert profile["basics"]["name"] == "Damien Yu"
    assert profile["experience"] == []


def test_fill_empty_does_not_wipe_cv_experience() -> None:
    existing = {
        "basics": {"name": "Pat Lee", "linkedin": "", "location": "Hong Kong"},
        "experience": [{"company": "MTR", "role": "Engineer"}],
        "education": [],
    }
    incoming = skeleton_profile("other-user", "https://www.linkedin.com/in/other-user")
    incoming["experience"] = [{"company": "HSBC", "role": "Analyst"}]
    incoming["basics"]["name"] = "Other User"
    merged = merge_fill_empty(existing, incoming)
    assert merged["basics"]["name"] == "Pat Lee"
    assert merged["basics"]["linkedin"] == "other-user"
    assert merged["experience"][0]["company"] == "MTR"


def test_fill_empty_replaces_placeholder_name() -> None:
    existing = {"basics": {"name": "Your Name", "linkedin": ""}, "experience": []}
    incoming = skeleton_profile("damien-yu", "https://www.linkedin.com/in/damien-yu")
    merged = merge_fill_empty(existing, incoming)
    assert merged["basics"]["name"] == "Damien Yu"
    assert merged["basics"]["linkedin"] == "damien-yu"


def test_mcp_merge_fills_empty_experience_and_headline() -> None:
    existing = {
        "basics": {"name": "Lychee Lai", "linkedin": "lychee-lai", "location": "Hong Kong"},
        "experience": [],
        "education": [{"institution": "Some School", "degree": "", "year": ""}],
    }
    incoming = {
        "basics": {
            "name": "Lychee Lai",
            "headline": "Data scientist",
            "summary": "About text",
            "linkedin": "lychee-lai",
            "location": "Hong Kong",
        },
        "experience": [
            {
                "company": "HKPC",
                "role": "Researcher",
                "period": "2024 - Present",
                "roles": [{"role": "Researcher", "period": "2024 - Present", "highlights": []}],
            }
        ],
        "education": [
            {"institution": "HKU", "degree": "MSc", "year": "2020 - 2022"},
            {"institution": "CUHK", "degree": "BSc", "year": "2016 - 2020"},
        ],
    }
    merged = merge_linkedin_mcp(existing, incoming)
    assert merged["basics"]["headline"] == "Data scientist"
    assert merged["basics"]["summary"] == "About text"
    assert merged["experience"][0]["company"] == "HKPC"
    assert len(merged["education"]) == 2


def test_normalize_languages_from_basics_dicts() -> None:
    from linkedin_bootstrap import normalize_profile_languages

    out = normalize_profile_languages(
        {
            "basics": {
                "name": "Lychee Lai",
                "languages": [
                    {"name": "Cantonese", "proficiency": "Native or bilingual proficiency"},
                    {"name": "English", "proficiency": "Professional working proficiency"},
                ],
            },
            "languages": [],
        }
    )
    assert out["languages"][0]["name"] == "Cantonese"
    assert out["basics"]["languages"][0] == "Cantonese (Native or bilingual proficiency)"
    assert all(isinstance(label, str) for label in out["basics"]["languages"])

