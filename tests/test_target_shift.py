"""Tests for Milo major-target-shift job recall gates.

# Ref: src/validators/target_shift.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATORS = Path(__file__).resolve().parents[1] / "src" / "validators"
if str(_VALIDATORS) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS))

from target_shift import (
    collect_target_terms,
    format_jobs_for_milo,
    is_direct_target_statement,
    is_major_target_shift,
    matching_job_where,
    merge_stated_targets,
    should_retrieve_stored_jobs,
    unique_target_terms,
)


def test_unique_and_normalize() -> None:
    assert unique_target_terms(["FinTech", "fintech", " IoT "]) == ["fintech", "iot"]


def test_casual_chat_does_not_retrieve() -> None:
    old = ["iot", "proptech"]
    new = ["iot", "proptech"]
    extracted = {"career_context_notes": ["likes hybrid"]}
    assert should_retrieve_stored_jobs(
        old_terms=old,
        new_terms=new,
        extracted=extracted,
        user_message="我下星期比較忙",
    ) is False


def test_small_add_is_not_major() -> None:
    old = ["iot", "proptech", "utilities", "fintech"]
    new = ["iot", "proptech", "utilities", "fintech", "insurtech"]
    assert is_major_target_shift(old, new) is False


def test_pivot_is_major_and_direct() -> None:
    old = ["iot", "proptech", "construction"]
    new = ["fintech", "backend", "banking"]
    extracted = {"target_industries": ["FinTech", "Banking"]}
    assert is_direct_target_statement(extracted, "轉做 FinTech 後端，不再找工地 IoT") is True
    assert is_major_target_shift(old, new) is True
    assert should_retrieve_stored_jobs(
        old_terms=old,
        new_terms=new,
        extracted=extracted,
        user_message="轉做 FinTech 後端，不再找工地 IoT",
    ) is True


def test_direct_marker_without_extracted_still_direct() -> None:
    assert is_direct_target_statement({}, "我想改做 data engineer") is True


def test_matching_where_empty() -> None:
    sql, params = matching_job_where([])
    assert sql == ""
    assert params == []


def test_matching_where_parameterized() -> None:
    sql, params = matching_job_where(["FinTech", "backend"])
    assert "job_title" in sql
    assert sql.count("?") == len(params)
    assert all(p.startswith("%") and p.endswith("%") for p in params)


def test_format_jobs_empty_explains() -> None:
    text = format_jobs_for_milo([])
    assert "Rex" in text
    assert "資料庫" in text


def test_format_jobs_lists_rows() -> None:
    text = format_jobs_for_milo([
        {
            "company_name": "HSBC",
            "job_title": "Backend Engineer",
            "match_score": 88,
            "target_industry": "FinTech",
            "job_url": "https://example.com/job/1",
        }
    ])
    assert "HSBC" in text
    assert "88" in text
    assert "https://example.com/job/1" in text


def test_collect_and_merge_stated_targets() -> None:
    profile = {
        "acceptance_context": {"target_industries": ["IoT"], "role_archetypes": []},
        "basics": {"target_roles": ["Platform Engineer"]},
    }
    merge_stated_targets(profile, {"target_industries": ["FinTech"]})
    terms = collect_target_terms(profile, {"target_industries": ["FinTech"]})
    assert "iot" in terms
    assert "fintech" in terms
    assert "platform engineer" in terms
    assert profile["stated_targets"]["industries"] == ["fintech"]
