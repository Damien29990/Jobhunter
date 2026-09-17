"""Canonical env key aliases."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_AGENTS = Path(__file__).resolve().parents[1] / "src" / "agents"
if str(_AGENTS) not in sys.path:
    sys.path.insert(0, str(_AGENTS))

from env_keys import deepseek_api_key, tavily_api_key


def test_canonical_names_preferred() -> None:
    os.environ.pop("TAVILY_API_KEY", None)
    os.environ.pop("TAVILY_KEY", None)
    os.environ.pop("DEEPSEEK_API_KEY", None)
    os.environ.pop("DEEPSEEK_KEY", None)
    os.environ.pop("OPENAI_API_KEY", None)
    os.environ["TAVILY_KEY"] = "tvly-alias"
    os.environ["OPENAI_API_KEY"] = "sk-alias"
    assert tavily_api_key() == "tvly-alias"
    assert os.environ["TAVILY_API_KEY"] == "tvly-alias"
    assert deepseek_api_key() == "sk-alias"
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-alias"
    for key in ("TAVILY_API_KEY", "TAVILY_KEY", "DEEPSEEK_API_KEY", "DEEPSEEK_KEY", "OPENAI_API_KEY"):
        os.environ.pop(key, None)
