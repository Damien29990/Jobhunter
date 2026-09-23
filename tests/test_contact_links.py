"""Username-only GitHub / LinkedIn values must expand to profile URLs."""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATORS = Path(__file__).resolve().parents[1] / "src" / "validators"
if str(_VALIDATORS) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS))

from contact_links import (
    contact_typst_markup,
    github_profile_url,
    linkedin_profile_url,
    website_url,
)


def test_github_username_only() -> None:
    assert github_profile_url("octocat") == "https://github.com/octocat"
    assert github_profile_url("@octocat") == "https://github.com/octocat"


def test_github_from_host_and_url() -> None:
    assert github_profile_url("github.com/octocat") == "https://github.com/octocat"
    assert github_profile_url("https://github.com/octocat/") == "https://github.com/octocat"


def test_linkedin_username_only() -> None:
    assert linkedin_profile_url("damien-yu") == "https://www.linkedin.com/in/damien-yu"
    assert linkedin_profile_url("@damien-yu") == "https://www.linkedin.com/in/damien-yu"


def test_linkedin_from_in_path_and_url() -> None:
    assert linkedin_profile_url("in/damien-yu") == "https://www.linkedin.com/in/damien-yu"
    assert (
        linkedin_profile_url("https://www.linkedin.com/in/damien-yu/")
        == "https://www.linkedin.com/in/damien-yu"
    )
    assert (
        linkedin_profile_url("https://hk.linkedin.com/in/damien-yu")
        == "https://www.linkedin.com/in/damien-yu"
    )


def test_linkedin_company_url_is_not_a_username() -> None:
    from contact_links import is_valid_linkedin_username

    assert is_valid_linkedin_username("https://www.linkedin.com/company/mtr") is False


def test_website_adds_https() -> None:
    assert website_url("example.com") == "https://example.com"
    assert website_url("https://example.com/cv") == "https://example.com/cv"


def test_typst_header_contains_clickable_github_and_linkedin() -> None:
    markup = contact_typst_markup(
        {
            "email": "a@b.com",
            "github": "octocat",
            "linkedin": "damien-yu",
        }
    )
    assert '#link("https://github.com/octocat")' in markup
    assert '#link("https://www.linkedin.com/in/damien-yu")' in markup
    assert '#link("mailto:a@b.com")' in markup
