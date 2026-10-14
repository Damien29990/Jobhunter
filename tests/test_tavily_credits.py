"""Tavily credit weights and Dana lane count."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_VALIDATORS = _ROOT / "src" / "validators"
_AGENTS = _ROOT / "src" / "agents"
for p in (_VALIDATORS, _AGENTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from tavily_credits import (  # noqa: E402
    tavily_extract_credits,
    tavily_search_credits,
    tavily_search_depth,
)
from tavily_usage import instrument_tavily, reset_tavily, snapshot_tavily  # noqa: E402
from agent_run_store import persist_agent_run  # noqa: E402


def test_search_credits_advanced_costs_two() -> None:
    assert tavily_search_credits("basic") == 1
    assert tavily_search_credits("advanced") == 2


def test_extract_credits_per_five_urls() -> None:
    assert tavily_extract_credits(1) == 1
    assert tavily_extract_credits(5) == 1
    assert tavily_extract_credits(6) == 2


def test_instrument_counts_failed_search() -> None:
    reset_tavily()

    class Fake:
        def search(self, **kwargs):
            raise RuntimeError("This request exceeds your plan's set usage limit.")

        def extract(self, **kwargs):
            return {"results": []}

    client = instrument_tavily(Fake())
    try:
        client.search(query="x", search_depth="advanced")
    except RuntimeError:
        pass
    snap = snapshot_tavily()
    assert snap["tavily_calls"] == 1
    assert snap["tavily_credits_est"] == 2
    assert snap["tavily_search_calls"] == 1


def test_persist_agent_run_roundtrip(tmp_path) -> None:
    db = tmp_path / "job_agent.db"
    persist_agent_run(
        {
            "agent": "Dana",
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
            "llm_calls": 1,
            "tavily_calls": 4,
            "tavily_credits_est": 4,
            "tavily_search_calls": 4,
            "tavily_extract_calls": 0,
        },
        db_path=db,
    )
    import sqlite3

    row = sqlite3.connect(str(db)).execute(
        "SELECT agent, tavily_credits_est, total_tokens FROM agent_runs"
    ).fetchone()
    assert row == ("Dana", 4, 15)


def test_default_search_depth_is_basic(monkeypatch) -> None:
    monkeypatch.delenv("TAVILY_SEARCH_DEPTH", raising=False)
    assert tavily_search_depth() == "basic"


def test_default_dana_alias_limit_is_one() -> None:
    from tavily_credits import dana_tavily_alias_limit

    assert dana_tavily_alias_limit() == 1
