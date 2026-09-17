"""Automated pipeline scheduler — APScheduler with cron triggers.

Runs the full LangGraph pipeline (Milo → Rex → Dana → Leo → Clara) on a
configurable schedule (default: twice daily at 9am + 6pm HKT). Sends Telegram
notifications after each agent completes. Can also be triggered manually
via run_now() or the dashboard "Run Now" button.

# Ref: workspace rule — deterministic scheduling, no LLM guessing.
"""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

HK_TZ = ZoneInfo("Asia/Hong_Kong")

# Lazy import APScheduler (not needed if scheduler never starts)
_scheduler = None
_scheduler_lock = threading.Lock()
_last_run: Optional[dict] = None
_last_result: Optional[dict] = None
_running = False


def _parse_cron_hours() -> list[int]:
    """Parse SCHEDULER_HOURS env var (e.g. '9,18' → [9, 18])."""
    raw = os.environ.get("SCHEDULER_HOURS", "9,18")
    try:
        return [int(h.strip()) for h in raw.split(",") if h.strip()]
    except ValueError:
        return [9, 18]


def _run_pipeline_async():
    """Run the full pipeline in a background thread. Updates _running/_last_result."""
    global _running, _last_run, _last_result
    _running = True
    _last_run = {"started_at": datetime.now(HK_TZ).isoformat(), "status": "running"}
    try:
        from pipeline_graph import run_pipeline
        result = run_pipeline(
            candidate_id=os.environ.get("SCHEDULER_CANDIDATE_ID", "default"),
            profile_path=os.environ.get("SCHEDULER_PROFILE_PATH", ""),
            query=os.environ.get("SCHEDULER_QUERY", ""),
        )
        _last_result = {
            "finished_at": datetime.now(HK_TZ).isoformat(),
            "status": "completed",
            "errors": result.get("errors", []),
            "jobs_found": len(result.get("jobs_found", [])),
            "dossiers": len(result.get("dossiers", [])),
            "cv_results": len(result.get("cv_results", [])),
            "checklist_results": len(result.get("checklist_results", [])),
            "node_metrics": result.get("node_metrics", {}),
        }
    except Exception as exc:
        _last_result = {
            "finished_at": datetime.now(HK_TZ).isoformat(),
            "status": "failed",
            "error": str(exc),
        }
    finally:
        _running = False
        _last_run["finished_at"] = datetime.now(HK_TZ).isoformat()
        _last_run["status"] = _last_result["status"] if _last_result else "failed"


def start():
    """Start the APScheduler with cron triggers for SCHEDULER_HOURS."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler and _scheduler.running:
            return {"ok": False, "error": "scheduler already running"}
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
        except ImportError:
            return {"ok": False, "error": "apscheduler not installed"}
        _scheduler = BackgroundScheduler(timezone=HK_TZ)
        hours = _parse_cron_hours()
        for h in hours:
            _scheduler.add_job(
                _run_pipeline_async,
                trigger=CronTrigger(hour=h, minute=0, timezone=HK_TZ),
                id=f"pipeline_{h}",
                name=f"Pipeline run at {h}:00 HKT",
            )
        _scheduler.start()
    try:
        from telegram_notifier import send_startup
        send_startup()
    except Exception:
        pass
    return {"ok": True, "hours": hours, "next_runs": get_next_run_times()}


def stop():
    """Stop the scheduler."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=False)
            _scheduler = None
            return {"ok": True, "message": "scheduler stopped"}
    return {"ok": False, "error": "scheduler not running"}


def run_now():
    """Trigger an immediate pipeline run in a background thread."""
    if _running:
        return {"ok": False, "error": "pipeline already running"}
    t = threading.Thread(target=_run_pipeline_async, daemon=True)
    t.start()
    return {"ok": True, "message": "pipeline started"}


def configure(hours: list[int]):
    """Update the cron schedule. Requires restart."""
    os.environ["SCHEDULER_HOURS"] = ",".join(str(h) for h in hours)
    if _scheduler and _scheduler.running:
        stop()
        return start()
    return {"ok": True, "hours": hours, "message": "configured (scheduler not running)"}


def status() -> dict:
    """Return scheduler status, next run times, last run, last result."""
    running = _scheduler is not None and _scheduler.running
    return {
        "running": running,
        "pipeline_running": _running,
        "hours": _parse_cron_hours(),
        "next_runs": get_next_run_times() if running else [],
        "last_run": _last_run,
        "last_result": _last_result,
    }


def get_next_run_times() -> list[str]:
    """Get ISO timestamps for the next scheduled runs."""
    if not _scheduler or not _scheduler.running:
        return []
    jobs = _scheduler.get_jobs()
    return [
        job.next_run_time.isoformat() if job.next_run_time else "unknown"
        for job in jobs
    ]
