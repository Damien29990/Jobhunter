"""Live agent presence for the dashboard (LangGraph + subprocess).

LangGraph runs in-process so AgentRunner PIDs stay IDLE. Nodes call
mark_working / mark_idle; GET /api/agents/status overlays WORKING.

# Ref: office characters must walk whenever an agent is actually running
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from datetime import datetime
from zoneinfo import ZoneInfo

_LOCK = threading.Lock()
_STATE: dict[str, dict[str, str]] = {}
_AGENT_KEYS = ("milo", "rex", "dana", "leo", "clara")
_HK = ZoneInfo("Asia/Hong_Kong")


def _now() -> str:
    return datetime.now(_HK).isoformat()


def mark_working(agent_key: str, message: str = "") -> None:
    key = (agent_key or "").strip().lower()
    if key not in _AGENT_KEYS:
        return
    with _LOCK:
        _STATE[key] = {
            "state": "WORKING",
            "message": message or f"LangGraph: {key}",
            "started_at": _now(),
        }


def mark_idle(agent_key: str, *, failed: bool = False) -> None:
    key = (agent_key or "").strip().lower()
    if key not in _AGENT_KEYS:
        return
    with _LOCK:
        if failed:
            prev = _STATE.get(key) or {}
            _STATE[key] = {
                "state": "FAILED",
                "message": prev.get("message") or f"{key} failed",
                "started_at": prev.get("started_at") or _now(),
            }
        else:
            _STATE.pop(key, None)


def snapshot() -> dict[str, dict[str, str]]:
    with _LOCK:
        return {k: dict(v) for k, v in _STATE.items()}


@contextmanager
def agent_busy(agent_key: str, message: str = "") -> Iterator[None]:
    mark_working(agent_key, message)
    try:
        yield
    except Exception:
        mark_idle(agent_key, failed=True)
        raise
    else:
        mark_idle(agent_key)
