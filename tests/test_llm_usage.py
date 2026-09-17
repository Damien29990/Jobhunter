"""LLM usage meter — OpenAI-style usage and estimate fallback."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_AGENTS = Path(__file__).resolve().parents[1] / "src" / "agents"
if str(_AGENTS) not in sys.path:
    sys.path.insert(0, str(_AGENTS))

from llm_usage import record_chat_completion, record_ollama_payload, reset_usage, snapshot_usage


def test_openai_usage_is_counted() -> None:
    reset_usage("Rex")
    record_chat_completion(
        SimpleNamespace(usage=SimpleNamespace(prompt_tokens=100, completion_tokens=20))
    )
    snap = snapshot_usage()
    assert snap["prompt_tokens"] == 100
    assert snap["completion_tokens"] == 20
    assert snap["total_tokens"] == 120
    assert snap["estimated"] is False


def test_ollama_eval_counts() -> None:
    reset_usage("Milo")
    record_ollama_payload({"prompt_eval_count": 40, "eval_count": 12, "response": "{}"})
    snap = snapshot_usage()
    assert snap["prompt_tokens"] == 40
    assert snap["completion_tokens"] == 12
