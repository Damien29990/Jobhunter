"""Structured per-agent activity logger.

Agents own their own milestones in ``output/agent_activity.txt``. Each line is
plain text, append-only, and follows the format::

    [<HK ISO 8601>] [<SOURCE>] [<LEVEL>] <message>

where SOURCE ∈ {Milo, Rex, Dana, Leo, Clara, SYSTEM} and
LEVEL ∈ {INFO, WARN, ERROR, START, EXIT}.

This module is the single write helper used by both the agent scripts (via
``log_activity`` / ``log_agent``) and the runner (via ``log_system``). It is
thread-safe (module-level lock) and never raises — logging must not crash an
agent or a watcher thread.

# Ref: workspace rule — Asia/Hong_Kong (UTC+8) ISO 8601 timestamps; deterministic
write helper separated from LLM logic.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# PROJECT_ROOT is the Jobhunter repo root: src/agents/activity_logger.py
#   parents[0] = src/agents
#   parents[1] = src
#   parents[2] = <repo root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_FILE = PROJECT_ROOT / "output" / "agent_activity.txt"

# Ref: workspace rule — Asia/Hong_Kong (UTC+8) timezone standard.
HK_TZ = ZoneInfo("Asia/Hong_Kong")

_LOG_LOCK = threading.Lock()

# Canonical source/level forms. Input is matched case-insensitively (coerced
# to upper for the lookup) but the CANONICAL mixed-case form is written to the
# file so the frontend (which keys colors on "Rex"/"Dana"/"Leo"/"Clara") and the
# spec's SOURCE set ({Rex, Dana, Leo, Clara, SYSTEM}) both line up.
# Ref: workspace rule — source/level coercion; deterministic write helper.
_VALID_SOURCES = ("Milo", "Rex", "Dana", "Leo", "Clara", "SYSTEM")
_VALID_LEVELS = ("INFO", "WARN", "ERROR", "START", "EXIT")
_SOURCE_CANONICAL = {s.upper(): s for s in _VALID_SOURCES}
_LEVEL_CANONICAL = {lvl.upper(): lvl for lvl in _VALID_LEVELS}


def log_activity(source: str, message: str, level: str = "INFO") -> None:
    """Append one structured activity line to the shared log file.

    Format: ``[<HK ISO 8601>] [<SOURCE>] [<LEVEL>] <message>``

    Thread-safe (module-level lock) since up to 4 agent watcher threads plus
    the agents themselves may write concurrently. Never raises — logging
    must not crash an agent or a watcher.

    Source/level are matched case-insensitively (coerced to upper for the
    lookup) and the canonical form is written; an unknown source defaults to
    ``SYSTEM`` and an unknown level defaults to ``INFO``.

    # Ref: workspace rule — Asia/Hong_Kong (UTC+8) ISO 8601 timestamps.
    """
    try:
        src = _SOURCE_CANONICAL.get((source or "").strip().upper(), "SYSTEM")
        lvl = _LEVEL_CANONICAL.get((level or "").strip().upper(), "INFO")
        stamp = datetime.now(HK_TZ).isoformat()
        line = f"[{stamp}] [{src}] [{lvl}] {message}\n"
        with _LOG_LOCK:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(line)
    except Exception:
        # Logging must never raise into agent or watcher code.
        pass


def log_system(message: str, level: str = "INFO") -> None:
    """Convenience wrapper for SYSTEM-sourced events (runner lifecycle)."""
    log_activity("SYSTEM", message, level)


def log_agent(agent_character: str, message: str, level: str = "INFO") -> None:
    """Convenience wrapper for an agent-sourced milestone (Rex/Dana/Leo/Clara)."""
    log_activity(agent_character, message, level)
