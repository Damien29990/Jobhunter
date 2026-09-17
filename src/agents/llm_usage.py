"""Accumulate LLM token usage for one agent process.

DeepSeek (OpenAI SDK) and Ollama expose usage on the response; the pipeline
previously recorded TokenMetrics with prompt_tokens=0 always.

# Ref: pipeline_state.TokenMetrics
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_DIR = PROJECT_ROOT / "output" / "telemetry"

_LOCK = threading.Lock()
_prompt = 0
_completion = 0
_calls = 0
_estimated = False
_agent = ""


def reset_usage(agent: str = "") -> None:
    """Start a fresh counter for this agent run."""
    global _prompt, _completion, _calls, _estimated, _agent
    with _LOCK:
        _prompt = 0
        _completion = 0
        _calls = 0
        _estimated = False
        _agent = agent or _agent


def _add(prompt: int, completion: int, estimated: bool = False) -> None:
    global _prompt, _completion, _calls, _estimated
    with _LOCK:
        _prompt += max(0, int(prompt or 0))
        _completion += max(0, int(completion or 0))
        _calls += 1
        if estimated:
            _estimated = True


def snapshot_usage() -> dict[str, int | str | bool]:
    with _LOCK:
        return {
            "agent": _agent,
            "prompt_tokens": _prompt,
            "completion_tokens": _completion,
            "total_tokens": _prompt + _completion,
            "llm_calls": _calls,
            "estimated": _estimated,
        }


def _estimate_tokens(text: str) -> int:
    """Rough char/4 fallback when the vendor omits usage."""
    return max(1, (len(text or "") + 3) // 4)


def record_chat_completion(response: Any, messages: Optional[list] = None) -> None:
    """Read OpenAI/DeepSeek usage; estimate if the field is missing."""
    usage = getattr(response, "usage", None)
    prompt = completion = 0
    if usage is not None:
        prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion = int(getattr(usage, "completion_tokens", 0) or 0)
        if prompt == 0 and completion == 0 and isinstance(usage, dict):
            prompt = int(usage.get("prompt_tokens") or 0)
            completion = int(usage.get("completion_tokens") or 0)
    estimated = False
    if prompt == 0 and completion == 0:
        estimated = True
        blob = ""
        for msg in messages or []:
            if isinstance(msg, dict):
                blob += str(msg.get("content") or "")
        try:
            blob += str(response.choices[0].message.content or "")
        except Exception:
            pass
        prompt = _estimate_tokens(blob)
        completion = 0
    _add(prompt, completion, estimated=estimated)


def record_ollama_payload(payload: dict) -> None:
    """Ollama /api/generate returns prompt_eval_count + eval_count."""
    if not isinstance(payload, dict):
        return
    prompt = int(payload.get("prompt_eval_count") or 0)
    completion = int(payload.get("eval_count") or 0)
    estimated = False
    if prompt == 0 and completion == 0:
        estimated = True
        prompt = _estimate_tokens(str(payload.get("response") or ""))
    _add(prompt, completion, estimated=estimated)


def instrument_openai(client: Any) -> Any:
    """Wrap chat.completions.create so every DeepSeek call is counted."""
    completions = client.chat.completions
    if getattr(completions, "_jobhunter_usage", False):
        return client
    original = completions.create

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        response = original(*args, **kwargs)
        record_chat_completion(response, messages=kwargs.get("messages"))
        return response

    completions.create = wrapped  # type: ignore[method-assign]
    completions._jobhunter_usage = True
    return client


def finalize_usage(agent: str) -> dict[str, int | str | bool]:
    """Print a parseable TOKENS line, persist JSON, return the snapshot."""
    global _agent
    with _LOCK:
        if agent:
            _agent = agent
    snap = snapshot_usage()
    line = (
        f"TOKENS agent={snap['agent'] or agent} "
        f"prompt={snap['prompt_tokens']} completion={snap['completion_tokens']} "
        f"total={snap['total_tokens']} calls={snap['llm_calls']}"
        f"{' estimated=1' if snap['estimated'] else ''}"
    )
    print(line)
    try:
        TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
        key = (str(snap["agent"] or agent or "agent")).lower()
        path = TELEMETRY_DIR / f"{key}_last.json"
        path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
    except Exception:
        pass
    try:
        from activity_logger import log_activity

        log_activity(
            agent or "SYSTEM",
            f"Tokens prompt={snap['prompt_tokens']} completion={snap['completion_tokens']} "
            f"total={snap['total_tokens']}",
        )
    except Exception:
        pass
    return snap
