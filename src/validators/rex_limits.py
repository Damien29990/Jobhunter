"""Rex run caps — Tavily API count per scan; JD DeepSeek evals are uncapped.

max_tokens only limits DeepSeek *completion*. Search+extract calls dominate
Tavily spend; each lane search and category extract counts as one call.

# Ref: talent_scout_agent_2.run_pipeline
"""

from __future__ import annotations

import os


def _positive_int(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(lo, min(hi, value))


def rex_max_search_tracks(default: int = 5) -> int:
    """How many horizon tracks Rex searches this run. # Ref: MAX_SEARCH_TRACKS"""
    return _positive_int("REX_MAX_SEARCH_TRACKS", default, lo=3, hi=7)


def rex_tavily_max_calls() -> int:
    """Tavily search+extract API calls per Rex scan (JD evals are uncapped)."""
    return _positive_int("REX_TAVILY_MAX_CALLS", 16, lo=4, hi=80)


def rex_max_completion_tokens() -> int:
    """chat.completions max_tokens for Rex JSON calls."""
    return _positive_int("REX_MAX_COMPLETION_TOKENS", 2048, lo=256, hi=8192)


def rex_eval_jd_chars() -> int:
    """JD characters sent to DeepSeek (full text still stored in SQLite)."""
    return _positive_int("REX_EVAL_JD_CHARS", 8000, lo=2000, hi=40000)


def rex_tavily_max_results() -> int:
    """Tavily hits per search lane per track. # Ref: search_verified_jobs"""
    return _positive_int("REX_TAVILY_MAX_RESULTS", 5, lo=3, hi=12)
