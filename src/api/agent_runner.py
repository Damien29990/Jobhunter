"""Subprocess manager for agent runs.

Spawns the real agent scripts with their REAL CLI args (only Agent 1 accepts
--profile; Agents 2-4 have no profile concept yet). Tracks per-agent state
(IDLE/WORKING/FAILED) in memory and tails recent stdout/stderr lines for the
pixel office status bubbles.

# Ref: workspace rule — deterministic logic separation; the dashboard triggers
agents, agents own DB writes. The dashboard never writes to job_agent.db.
"""
from __future__ import annotations

import os
import json
import re
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AGENTS_DIR = PROJECT_ROOT / "src" / "agents"
# activity_logger.py lives in src/agents; put it on sys.path so the runner can
# share the same thread-safe write helper as the agents themselves.
if str(AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(AGENTS_DIR))
PROFILES_DIR = PROJECT_ROOT / "config" / "profiles"
DEFAULT_PROFILE = PROJECT_ROOT / "config" / "master_profile.json"

# Each agent: key -> (character, script, accepts_profile)
AGENTS = {
    "milo": ("Milo", "milo_intake.py", False),
    "rex": ("Rex", "talent_scout_agent_2.py", True),
    "dana": ("Dana", "due_diligence_agent.py", False),
    "leo": ("Leo", "cv_generator_agent.py", False),
    "clara": ("Clara", "cert_matcher_agent.py", False),
}

MAX_TAIL_LINES = 40
TOKENS_RE = re.compile(
    r"TOKENS agent=\S+ prompt=(\d+) completion=(\d+) total=(\d+)"
)

# Unified cross-agent log — append-only plain text, one line per activity.
# Format: ``[<HK ISO 8601>] [<SOURCE>] [<LEVEL>] <message>`` where
# SOURCE ∈ {Rex, Dana, Leo, Clara, SYSTEM} and LEVEL ∈ {INFO, WARN, ERROR, START, EXIT}.
# Ref: workspace rule — Asia/Hong_Kong (UTC+8) ISO 8601; deterministic write helper.
#
# Division of responsibility (avoids double-writing):
#   - Agents own their .txt milestones: they call log_activity("Rex", ...) directly.
#   - agent_runner owns SYSTEM .txt events (triggered/stopped/exit) via log_system,
#     and keeps the in-memory rt.tail (for the UI status bubbles) separate.
# The write helper itself lives in src/agents/activity_logger.py so agents and
# the runner share a single thread-safe append path. LOG_FILE is re-exported
# here for backward compatibility with server.py (which imports it from us).
from activity_logger import LOG_FILE, log_system  # noqa: E402


def _parse_tokens_line(line: str) -> Optional[tuple[int, int, int]]:
    match = TOKENS_RE.search(line or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _telemetry_file(agent_key: str) -> Path:
    return PROJECT_ROOT / "output" / "telemetry" / f"{agent_key}_last.json"


def _load_telemetry_tokens(agent_key: str) -> dict:
    path = _telemetry_file(agent_key)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "prompt_tokens": int(payload.get("prompt_tokens") or 0),
        "completion_tokens": int(payload.get("completion_tokens") or 0),
        "total_tokens": int(payload.get("total_tokens") or 0),
    }


@dataclass
class AgentRuntime:
    agent: str
    character: str
    state: str = "IDLE"          # IDLE | WORKING | FAILED
    pid: Optional[int] = None
    started_at: Optional[str] = None
    message: Optional[str] = None
    tail: deque = field(default_factory=lambda: deque(maxlen=MAX_TAIL_LINES))
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    _proc: Optional[subprocess.Popen] = None
    _thread: Optional[threading.Thread] = None


@dataclass
class PipelineRuntime:
    state: str = "IDLE"          # IDLE | RUNNING | DONE | FAILED
    step: str = ""               # current agent key, "" when idle
    log: deque = field(default_factory=lambda: deque(maxlen=MAX_TAIL_LINES))
    _thread: Optional[threading.Thread] = None


class AgentRunner:
    """Thread-safe singleton-ish runner. One in-flight run per agent."""

    def __init__(self) -> None:
        self._rt: dict[str, AgentRuntime] = {
            key: AgentRuntime(agent=key, character=char)
            for key, (char, _script, _prof) in AGENTS.items()
        }
        self._lock = threading.Lock()
        self._pipeline = PipelineRuntime()

    # -- profile resolution -------------------------------------------------

    @staticmethod
    def resolve_profile_path(candidate_id: Optional[str]) -> Path:
        """Resolve a --profile path for Agent 1.

        Forward-compatible multi-user: if config/profiles/{id}.json exists use it,
        else fall back to config/master_profile.json. candidate_id may be None.
        """
        if candidate_id:
            cand = PROFILES_DIR / f"{candidate_id}.json"
            if cand.is_file():
                return cand
        if DEFAULT_PROFILE.is_file():
            return DEFAULT_PROFILE
        return DEFAULT_PROFILE  # let the agent raise if truly missing

    # -- command building ---------------------------------------------------

    def _build_cmd(self, agent_key: str, req) -> list[str]:
        _char, script, accepts_profile = AGENTS[agent_key]
        py = sys.executable or "python"
        cmd = [py, str(AGENTS_DIR / script)]

        if agent_key == "rex":
            if req.min_score is not None:
                cmd += ["--min-score", str(req.min_score)]
            if req.query:
                cmd += ["--query", req.query]
            if accepts_profile:
                cmd += ["--profile", str(self.resolve_profile_path(req.candidate_id))]
        elif agent_key == "dana":
            if req.min_score is not None:
                cmd += ["--min-score", str(req.min_score)]
            if req.force_refresh:
                cmd += ["--force-refresh"]
            if req.job_id is not None:
                cmd += ["--job-id", str(req.job_id)]
            if req.company:
                cmd += ["--company", req.company]
        elif agent_key == "leo":
            if req.job_id is not None:
                cmd += ["--job-id", str(req.job_id)]
            if req.company:
                cmd += ["--company", req.company]
            if req.min_score is not None:
                cmd += ["--min-score", str(req.min_score)]
            if getattr(req, "template", None):
                cmd += ["--template", str(req.template)]
        elif agent_key == "clara":
            if req.job_id is not None:
                cmd += ["--job-id", str(req.job_id)]
            if req.company:
                cmd += ["--company", req.company]
            if req.min_score is not None:
                cmd += ["--min-score", str(req.min_score)]
        elif agent_key == "milo":
            if req.query:
                cmd += ["--cv", req.query]  # reuse query field for CV path
            cmd += ["--profile", str(self.resolve_profile_path(req.candidate_id))]
        return cmd

    # -- run ----------------------------------------------------------------

    def start(self, agent_key: str, req) -> dict:
        with self._lock:
            rt = self._rt[agent_key]
            if rt.state == "WORKING":
                return {"ok": False, "error": f"{rt.character} is already WORKING"}

        cmd = self._build_cmd(agent_key, req)
        env = os.environ.copy()
        # Force UTF-8 std streams + UTF-8 mode so agent print() statements that
        # contain emoji don't crash under a cp950/cp1252 Windows console codepage.
        # (e.g. talent_scout_agent_2 prints 🦭 — cp950 can't encode it.)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        # Agents load .env themselves via load_dotenv, but pass through anyway.
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
            )
        except Exception as exc:  # pragma: no cover - spawn failure
            with self._lock:
                rt.state = "FAILED"
                rt.message = f"spawn failed: {exc}"
            return {"ok": False, "error": str(exc)}

        with self._lock:
            rt.state = "WORKING"
            rt.pid = proc.pid
            rt.started_at = time.strftime("%Y-%m-%dT%H:%M:%S+08:00")
            rt.message = " ".join(cmd)
            rt.tail.clear()
            rt.prompt_tokens = 0
            rt.completion_tokens = 0
            rt.total_tokens = 0
            rt._proc = proc
        # System event: agent triggered. Agents own their own .txt milestones;
        # the runner owns only SYSTEM lifecycle events.
        log_system(f"{rt.character} triggered: {rt.message}", level="START")

        t = threading.Thread(
            target=self._watch, args=(agent_key, proc), daemon=True
        )
        with self._lock:
            rt._thread = t
        t.start()
        return {"ok": True, "pid": proc.pid, "command": " ".join(cmd)}

    def _watch(self, agent_key: str, proc: subprocess.Popen) -> None:
        rt = self._rt[agent_key]
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.rstrip("\n")
                with self._lock:
                    rt.tail.append(line)
                    parsed = _parse_tokens_line(line)
                    if parsed:
                        rt.prompt_tokens, rt.completion_tokens, rt.total_tokens = parsed
        except Exception as exc:  # pragma: no cover
            with self._lock:
                rt.tail.append(f"[stream error] {exc}")
        finally:
            rc = proc.wait()
            extra = _load_telemetry_tokens(agent_key)
            with self._lock:
                rt.state = "FAILED" if rc not in (0, None) else "IDLE"
                rt.pid = None
                rt.tail.append(f"[exit code {rc}]")
                if extra.get("total_tokens") and not rt.total_tokens:
                    rt.prompt_tokens = extra["prompt_tokens"]
                    rt.completion_tokens = extra["completion_tokens"]
                    rt.total_tokens = extra["total_tokens"]
                rt._proc = None
            log_system(
                f"{rt.character} exited code {rc}",
                level="EXIT" if rc == 0 else "ERROR",
            )

    # -- status -------------------------------------------------------------

    def status(self, agent_key: str) -> dict:
        extra = _load_telemetry_tokens(agent_key)
        with self._lock:
            rt = self._rt[agent_key]
            prompt = rt.prompt_tokens or extra.get("prompt_tokens", 0)
            completion = rt.completion_tokens or extra.get("completion_tokens", 0)
            total = rt.total_tokens or extra.get("total_tokens", 0)
            return {
                "agent": agent_key,
                "character": rt.character,
                "state": rt.state,
                "pid": rt.pid,
                "started_at": rt.started_at,
                "message": rt.message,
                "last_lines": list(rt.tail),
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total,
            }

    def status_all(self) -> dict:
        return {key: self.status(key) for key in AGENTS}

    def stop(self, agent_key: str) -> dict:
        with self._lock:
            rt = self._rt[agent_key]
            proc = rt._proc
        if proc and proc.poll() is None:
            # System event: agent stopped by user. Logged before terminate so
            # the WARN line is persisted even if the process exits abruptly.
            log_system(f"{rt.character} stopped by user", level="WARN")
            proc.terminate()
            return {"ok": True, "message": f"terminated {rt.character}"}
        return {"ok": False, "error": f"{rt.character} not running"}

    # -- pipeline (run all 4 agents in sequence) -----------------------------

    PIPELINE_ORDER = ("milo", "rex", "dana", "leo", "clara")

    def run_pipeline(self, req) -> dict:
        """Run Rex → Dana → Leo → Clara in sequence, each after the previous
        completes. Uses one pipeline slot; rejects if any agent is already WORKING."""
        with self._lock:
            if self._pipeline.state == "RUNNING":
                return {"ok": False, "error": "pipeline already running"}
            if any(rt.state == "WORKING" for rt in self._rt.values()):
                return {"ok": False, "error": "an agent is already WORKING"}
            self._pipeline.state = "RUNNING"
            self._pipeline.step = ""
            self._pipeline.log.clear()
        t = threading.Thread(target=self._run_pipeline, args=(req,), daemon=True)
        with self._lock:
            self._pipeline._thread = t
        t.start()
        log_system("PIPELINE triggered", level="START")
        return {"ok": True}

    def _run_pipeline(self, req) -> None:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        try:
            for key in self.PIPELINE_ORDER:
                with self._lock:
                    self._pipeline.step = key
                self._pipeline.log.append(f"[pipeline] starting {key}")
                cmd = self._build_cmd(key, req)
                log_system(f"PIPELINE -> {key}", level="START")
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(PROJECT_ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=env,
                )
                with self._lock:
                    rt = self._rt[key]
                    rt.state = "WORKING"
                    rt.pid = proc.pid
                    rt.message = " ".join(cmd)
                    rt.tail.clear()
                    rt.prompt_tokens = 0
                    rt.completion_tokens = 0
                    rt.total_tokens = 0
                    rt._proc = proc
                assert proc.stdout is not None
                for line in proc.stdout:
                    line = line.rstrip("\n")
                    with self._lock:
                        rt.tail.append(line)
                        self._pipeline.log.append(f"[{key}] {line}")
                        parsed = _parse_tokens_line(line)
                        if parsed:
                            rt.prompt_tokens, rt.completion_tokens, rt.total_tokens = parsed
                rc = proc.wait()
                with self._lock:
                    rt.state = "FAILED" if rc not in (0, None) else "IDLE"
                    rt.pid = None
                    rt._proc = None
                log_system(
                    f"PIPELINE <- {key} exit {rc}",
                    level="EXIT" if rc == 0 else "ERROR",
                )
                self._pipeline.log.append(f"[pipeline] {key} exit code {rc}")
                if rc not in (0, None):
                    if _should_continue_after_agent_failure(key):
                        log_system(
                            f"{key} exited {rc} but downstream work remains — continuing",
                            level="WARN",
                        )
                        self._pipeline.log.append(
                            f"[pipeline] {key} failed; continuing with jobs already in DB"
                        )
                        continue
                    with self._lock:
                        self._pipeline.state = "FAILED"
                    _notify_desk_pipeline_finished(False, f"{key} exit {rc}")
                    return
            with self._lock:
                self._pipeline.state = "DONE"
                self._pipeline.step = ""
            self._pipeline.log.append("[pipeline] finished")
            _notify_desk_pipeline_finished(True)
        finally:
            with self._lock:
                self._pipeline.step = ""
                if self._pipeline.state == "RUNNING":
                    self._pipeline.state = "FAILED"

    def pipeline_status(self) -> dict:
        with self._lock:
            return {
                "state": self._pipeline.state,
                "step": self._pipeline.step,
                "log": list(self._pipeline.log),
            }

    def stop_pipeline(self) -> dict:
        with self._lock:
            if self._pipeline.state != "RUNNING":
                return {"ok": False, "error": "pipeline not running"}
        # Best-effort: stop the current agent; the pipeline thread will see the non-zero exit and stop.
        for key in self.PIPELINE_ORDER:
            self.stop(key)
        return {"ok": True}


def _funnel_counts() -> dict:
    """Read current SQLite funnel for the desk-pipeline Telegram summary."""
    import sqlite3

    db_path = PROJECT_ROOT / "job_agent.db"
    empty = {
        "jobs_found": 0,
        "dossiers": 0,
        "cv_generated": 0,
        "application_ready": 0,
    }
    if not db_path.is_file():
        return empty
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            def _count(sql: str) -> int:
                row = conn.execute(sql).fetchone()
                return int(row[0] if row and row[0] is not None else 0)

            return {
                "jobs_found": _count("SELECT COUNT(*) FROM job_postings"),
                "dossiers": _count("SELECT COUNT(*) FROM company_dossiers"),
                "cv_generated": _count(
                    "SELECT COUNT(*) FROM job_postings "
                    "WHERE cv_status IN ('MATERIALS_GENERATED', 'MATERIALS_RENDERED', 'generated')"
                ),
                "application_ready": _count(
                    "SELECT COUNT(*) FROM job_postings WHERE application_ready = 1"
                ),
            }
        finally:
            conn.close()
    except Exception:
        return empty


def _sql_count(sql: str) -> int:
    import sqlite3

    db_path = PROJECT_ROOT / "job_agent.db"
    if not db_path.is_file():
        return 0
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = conn.execute(sql).fetchone()
            return int(row[0] if row and row[0] is not None else 0)
        finally:
            conn.close()
    except Exception:
        return 0


def _should_continue_after_agent_failure(agent_key: str) -> bool:
    """Keep Finish Pipeline moving when later stages already have work in SQLite.

    # Ref: high-score jobs must not be stranded if Rex/Dana exits non-zero
    """
    if agent_key == "rex":
        return _sql_count(
            "SELECT COUNT(*) FROM job_postings "
            "WHERE COALESCE(match_score, 0) >= 80"
        ) > 0
    if agent_key == "dana":
        return _sql_count(
            "SELECT COUNT(*) FROM company_dossiers "
            "WHERE UPPER(COALESCE(vetting_verdict, '')) = 'PROCEED'"
        ) > 0
    if agent_key == "leo":
        return _sql_count(
            "SELECT COUNT(*) FROM job_postings "
            "WHERE cv_status IN ('MATERIALS_GENERATED', 'MATERIALS_RENDERED')"
        ) > 0
    return False


def _notify_desk_pipeline_finished(success: bool, error: str = "") -> None:
    """Telegram ping when dashboard Finish Pipeline ends.

    LangGraph already sends this; the desk subprocess path did not.
    # Ref: user — notify when finishing jobs
    """
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
        try:
            from .telegram_notifier import send_error, send_pipeline_summary
        except ImportError:
            from telegram_notifier import send_error, send_pipeline_summary

        if not success:
            send_error("Pipeline", error or "Finish Pipeline stopped with a failed agent")
            return
        counts = _funnel_counts()
        send_pipeline_summary(
            jobs_found=counts["jobs_found"],
            dossiers=counts["dossiers"],
            cv_generated=counts["cv_generated"],
            application_ready=counts["application_ready"],
        )
    except Exception:
        pass


runner = AgentRunner()
