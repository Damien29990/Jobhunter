"""Count Tavily search/extract calls and estimated credits for one agent run."""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Optional

_VALIDATORS_DIR = Path(__file__).resolve().parent.parent / "validators"
if str(_VALIDATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS_DIR))

from tavily_credits import (
    is_tavily_plan_limit_error,
    tavily_extract_credits,
    tavily_search_credits,
    tavily_search_depth,
)

_LOCK = threading.Lock()
_calls = 0
_credits = 0
_search = 0
_extract = 0
_budget: Optional[int] = None
_plan_exhausted = False


def reset_tavily() -> None:
    global _calls, _credits, _search, _extract, _budget, _plan_exhausted
    with _LOCK:
        _calls = 0
        _credits = 0
        _search = 0
        _extract = 0
        _budget = None
        _plan_exhausted = False


def begin_tavily_budget(max_calls: Optional[int]) -> None:
    global _budget, _plan_exhausted
    with _LOCK:
        _budget = int(max_calls) if max_calls is not None else None
        _plan_exhausted = False


def mark_tavily_plan_exhausted() -> None:
    global _plan_exhausted
    with _LOCK:
        _plan_exhausted = True


def tavily_plan_exhausted() -> bool:
    with _LOCK:
        return _plan_exhausted


def tavily_budget_exhausted() -> bool:
    with _LOCK:
        if _plan_exhausted:
            return True
        if _budget is None:
            return False
        return _calls >= _budget


def _record(kind: str, credits: int) -> None:
    global _calls, _credits, _search, _extract
    with _LOCK:
        _calls += 1
        _credits += max(0, int(credits))
        if kind == "extract":
            _extract += 1
        else:
            _search += 1


def snapshot_tavily() -> dict[str, int]:
    with _LOCK:
        return {
            "tavily_calls": _calls,
            "tavily_credits_est": _credits,
            "tavily_search_calls": _search,
            "tavily_extract_calls": _extract,
        }


def instrument_tavily(client: object) -> object:
    """Wrap search/extract so billed calls are counted even when they raise."""
    if getattr(client, "_jobhunter_tavily", False):
        return client
    original_search = client.search
    original_extract = client.extract

    def wrapped_search(*args: object, **kwargs: object) -> object:
        depth = str(kwargs.get("search_depth") or tavily_search_depth())
        _record("search", tavily_search_credits(depth))
        try:
            return original_search(*args, **kwargs)
        except Exception as exc:
            if is_tavily_plan_limit_error(exc):
                mark_tavily_plan_exhausted()
            raise

    def wrapped_extract(*args: object, **kwargs: object) -> object:
        urls = kwargs.get("urls")
        if urls is None and args:
            urls = args[0]
        n = len(urls) if isinstance(urls, list) else 1
        _record("extract", tavily_extract_credits(n))
        try:
            return original_extract(*args, **kwargs)
        except Exception as exc:
            if is_tavily_plan_limit_error(exc):
                mark_tavily_plan_exhausted()
            raise

    client.search = wrapped_search  # type: ignore[method-assign]
    client.extract = wrapped_extract  # type: ignore[method-assign]
    client._jobhunter_tavily = True  # type: ignore[attr-defined]
    return client
