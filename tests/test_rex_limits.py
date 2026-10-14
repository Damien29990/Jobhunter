"""Rex env caps for a faster scan."""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATORS = Path(__file__).resolve().parents[1] / "src" / "validators"
if str(_VALIDATORS) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS))

from rex_limits import (
    rex_eval_jd_chars,
    rex_max_completion_tokens,
    rex_max_search_tracks,
    rex_tavily_max_calls,
    rex_tavily_max_results,
)


def test_rex_limits_defaults(monkeypatch) -> None:
    for key in (
        "REX_MAX_SEARCH_TRACKS",
        "REX_TAVILY_MAX_CALLS",
        "REX_MAX_COMPLETION_TOKENS",
        "REX_EVAL_JD_CHARS",
        "REX_TAVILY_MAX_RESULTS",
    ):
        monkeypatch.delenv(key, raising=False)
    assert rex_max_search_tracks() == 5
    assert rex_tavily_max_calls() == 16
    assert rex_max_completion_tokens() == 2048
    assert rex_eval_jd_chars() == 8000
    assert rex_tavily_max_results() == 5


def test_rex_limits_clamp(monkeypatch) -> None:
    monkeypatch.setenv("REX_TAVILY_MAX_CALLS", "999")
    assert rex_tavily_max_calls() == 80
    monkeypatch.setenv("REX_MAX_SEARCH_TRACKS", "1")
    assert rex_max_search_tracks() == 3
