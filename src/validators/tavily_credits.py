"""Tavily credit weights and Dana/Rex spend knobs.

Tavily bills search_depth=advanced at 2 credits per search, basic at 1.
Extract bills 1 credit per 5 URLs (minimum 1 per request).

# Ref: Tavily Extract/Search credit table
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


def tavily_search_depth() -> str:
    """basic (1 credit) unless TAVILY_SEARCH_DEPTH=advanced (2 credits)."""
    raw = (os.environ.get("TAVILY_SEARCH_DEPTH") or "basic").strip().lower()
    return "advanced" if raw == "advanced" else "basic"


def tavily_search_credits(depth: str) -> int:
    return 2 if (depth or "").strip().lower() == "advanced" else 1


def tavily_extract_credits(url_count: int) -> int:
    n = max(1, int(url_count or 1))
    return (n + 4) // 5


def dana_tavily_max_calls() -> int:
    """Search+extract API calls per Dana run. # Ref: DANA_TAVILY_MAX_CALLS"""
    return _positive_int("DANA_TAVILY_MAX_CALLS", 40, lo=4, hi=200)


def dana_tavily_alias_limit() -> int:
    """Employer-name aliases × 3 lanes. 1 alias = 4 searches (3+general)."""
    return _positive_int("DANA_TAVILY_ALIAS_LIMIT", 1, lo=1, hi=3)


def is_tavily_plan_limit_error(exc: BaseException) -> bool:
    """True when Tavily refused the call because the monthly plan is spent."""
    msg = str(exc).lower()
    return "usage limit" in msg or "exceeds your plan" in msg
