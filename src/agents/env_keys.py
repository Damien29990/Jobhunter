"""Canonical API env keys for Jobhunter agents.

Canonical names (also in .env.example):
- TAVILY_API_KEY
- DEEPSEEK_API_KEY

Aliases are accepted so a misnamed key still works, then copied onto the
canonical name for the rest of the process.

# Ref: unify key names — do not mix OPENAI_API_KEY as the documented name
"""

from __future__ import annotations

import os

TAVILY_ALIASES = ("TAVILY_API_KEY", "TAVILY_KEY")
DEEPSEEK_ALIASES = ("DEEPSEEK_API_KEY", "DEEPSEEK_KEY", "OPENAI_API_KEY")


def _first_env(names: tuple[str, ...]) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def tavily_api_key() -> str:
    """Tavily search key. Canonical: TAVILY_API_KEY."""
    key = _first_env(TAVILY_ALIASES)
    if key and not (os.environ.get("TAVILY_API_KEY") or "").strip():
        os.environ["TAVILY_API_KEY"] = key
    return key


def deepseek_api_key() -> str:
    """DeepSeek Chat Completions key. Canonical: DEEPSEEK_API_KEY.

    OPENAI_API_KEY is only an alias because the SDK class is named OpenAI.
    """
    key = _first_env(DEEPSEEK_ALIASES)
    if key and not (os.environ.get("DEEPSEEK_API_KEY") or "").strip():
        os.environ["DEEPSEEK_API_KEY"] = key
    return key
