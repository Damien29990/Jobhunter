"""Telegram inbound commands for Clara follow-up (poll getUpdates).

Only TELEGRAM_CHAT_ID may command the bot. FastAPI must be hosting this
poller — if uvicorn is down, Telegram cannot get a reply from Jobhunter.

# Ref: Bot API getUpdates / callback_query
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from application_followup import (
    APPLICATION_STATUSES,
    application_status_label,
    normalize_application_status,
)

try:
    from .clara_followup import (
        apply_application_follow_up,
        get_clara_job,
        list_clara_jobs,
        status_token_ok,
    )
    from .telegram_notifier import (
        API_BASE,
        LAST_SEND_ERROR,
        _bot_token,
        _chat_id,
        _send_raw,
        clara_status_keyboard,
    )
except ImportError:
    from clara_followup import (  # type: ignore
        apply_application_follow_up,
        get_clara_job,
        list_clara_jobs,
        status_token_ok,
    )
    from telegram_notifier import (  # type: ignore
        API_BASE,
        LAST_SEND_ERROR,
        _bot_token,
        _chat_id,
        _send_raw,
        clara_status_keyboard,
    )

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OFFSET_PATH = PROJECT_ROOT / "output" / "telegram_offset.txt"

HELP = (
    "Clara follow-up via Telegram.\n"
    "/rex — paste a job URL; Rex scores it, then Dana → Leo → Clara if ≥80\n"
    "/rex https://hk.jobsdb.com/job/123 — same, one message\n"
    "/apply — Apply overview (◀️ Previous / Next ▶️, 2 hours)\n"
    "/clara — list jobs\n"
    "/clara 110 — show job + status buttons\n"
    "/clara 110 APPLIED — set status\n"
    "/note 110 your note\n"
    "/employer 110 employer reply\n"
    "Statuses: " + ", ".join(APPLICATION_STATUSES)
)

_CMD = re.compile(
    r"^\s*/?(clara|note|employer|help|start|apply)\b(?:\s+(\d+))?(?:\s+(\S+))?(?:\s+([\s\S]*))?$",
    re.I,
)
_REX = re.compile(r"^\s*/rex(?:@\w+)?\b(.*)$", re.I)
_HTTP_URL = re.compile(r"https?://[^\s<>]+", re.I)
_CB = re.compile(r"^c:(\d+):([A-Z_]+)$")
_APPLY_CB = re.compile(r"^a:([a-f0-9]{8}):(p|n|cv|cl|ed|l|x|j\d+)$")
HK_TZ = timezone(timedelta(hours=8))
REX_AWAIT_TTL = timedelta(minutes=10)

_stop = threading.Event()
_thread: Optional[threading.Thread] = None
_rex_lock = threading.Lock()
_rex_await_until: Optional[datetime] = None


class RexAwaitState(BaseModel):
    """Pending /rex until the next job URL. # Ref: Asia/Hong_Kong 10 min"""

    until: datetime = Field(...)


def _now_hk() -> datetime:
    return datetime.now(HK_TZ)


def extract_http_url(text: str) -> Optional[str]:
    """First http(s) URL in free text; strip trailing punctuation."""
    match = _HTTP_URL.search(text or "")
    if not match:
        return None
    return match.group(0).rstrip(").,]>\"'")


def _utf16_slice(text: str, offset: int, length: int) -> str:
    """Telegram entity offsets are UTF-16 code units. # Ref: Bot API MessageEntity"""
    encoded = (text or "").encode("utf-16-le")
    start = max(0, int(offset)) * 2
    end = start + max(0, int(length)) * 2
    return encoded[start:end].decode("utf-16-le", errors="replace")


def urls_from_message(message: dict) -> list[str]:
    """Prefer Telegram url / text_link entities, then regex on text."""
    text = str(message.get("text") or "")
    found: list[str] = []
    for ent in message.get("entities") or []:
        if not isinstance(ent, dict):
            continue
        kind = str(ent.get("type") or "")
        if kind == "text_link":
            href = str(ent.get("url") or "").strip()
            if href.startswith("http"):
                found.append(href.rstrip(").,]>\"'"))
        elif kind == "url":
            sliced = _utf16_slice(
                text, int(ent.get("offset") or 0), int(ent.get("length") or 0)
            ).strip()
            if sliced.startswith("http"):
                found.append(sliced.rstrip(").,]>\"'"))
    if not found:
        one = extract_http_url(text)
        if one:
            found.append(one)
    return found


def rex_await_active() -> bool:
    with _rex_lock:
        global _rex_await_until
        if _rex_await_until is None:
            return False
        if _now_hk() >= _rex_await_until:
            _rex_await_until = None
            return False
        return True


def set_rex_await() -> None:
    state = RexAwaitState(until=_now_hk() + REX_AWAIT_TTL)
    with _rex_lock:
        global _rex_await_until
        _rex_await_until = state.until


def clear_rex_await() -> None:
    with _rex_lock:
        global _rex_await_until
        _rex_await_until = None


def parse_clara_text(text: str) -> dict:
    """Parse a chat command into {kind, job_id, status, note, job_url}."""
    raw = (text or "").strip()
    if not raw:
        return {"kind": "empty"}
    rex = _REX.match(raw)
    if rex:
        url = extract_http_url(rex.group(1) or "")
        if url:
            return {"kind": "rex_ingest", "job_url": url}
        return {"kind": "rex_await"}
    m = _CMD.match(raw)
    if not m:
        return {"kind": "unknown"}
    verb = (m.group(1) or "").lower()
    job_raw = m.group(2)
    token = (m.group(3) or "").strip()
    rest = (m.group(4) or "").strip()
    job_id = int(job_raw) if job_raw else None
    if verb in {"help", "start"}:
        return {"kind": "help"}
    if verb == "apply":
        return {"kind": "apply_overview"}
    if verb == "clara":
        if job_id is None:
            return {"kind": "list"}
        if token and status_token_ok(token):
            return {
                "kind": "status",
                "job_id": job_id,
                "status": normalize_application_status(token),
            }
        if token:
            return {"kind": "show", "job_id": job_id, "error": "unknown status"}
        return {"kind": "show", "job_id": job_id}
    if verb == "note" and job_id is not None:
        note = " ".join(part for part in (token, rest) if part).strip()
        return {"kind": "note", "job_id": job_id, "note": note}
    if verb == "employer" and job_id is not None:
        note = " ".join(part for part in (token, rest) if part).strip()
        return {"kind": "employer", "job_id": job_id, "note": note}
    return {"kind": "help"}


def _reply(text: str, job_id: Optional[int] = None) -> bool:
    markup = clara_status_keyboard(job_id) if job_id else None
    return _send_raw(text.replace("\\", ""), markup)


def start_rex_ingest(job_url: str) -> str:
    """Spawn Rex --job-url; dashboard follow-up runs Dana → Leo → Clara if suitable.

    # Ref: talent_scout_agent_2.ingest_job_url · agent_runner._followup_pipeline_for_job
    """
    url = extract_http_url(job_url) or (job_url or "").strip()
    if not url:
        return "Send a job posting URL after /rex."
    try:
        from .agent_runner import runner
        from .models import AgentRunRequest
    except ImportError:
        from agent_runner import runner
        from models import AgentRunRequest

    status = runner.pipeline_status()
    if status.get("state") == "RUNNING":
        return (
            "Finish Pipeline is already running. Wait until it stops, then /rex again."
        )
    result = runner.start("rex", AgentRunRequest(job_url=url))
    if not result.get("ok"):
        return f"Rex could not start: {result.get('error') or 'busy'}"
    try:
        from activity_logger import log_system

        log_system(f"Telegram /rex ingest {url}", level="START")
    except Exception:
        pass
    return (
        f"Rex is ingesting:\n{url}\n"
        "If composite ≥ 80, Dana → Leo → Clara run for that job only (no Tavily search)."
    )


def handle_parsed(cmd: dict) -> str:
    """Run a parsed command; return user-facing reply (plain text)."""
    kind = cmd.get("kind")
    if kind == "rex_await":
        set_rex_await()
        return (
            "Send the job posting URL (JobsDB, LinkedIn, company careers, ATS).\n"
            "Waiting 10 minutes. Rex will score it; Dana → Leo → Clara follow if ≥ 80."
        )
    if kind == "rex_ingest":
        clear_rex_await()
        return start_rex_ingest(str(cmd.get("job_url") or ""))
    if kind in {"help", "empty", "unknown"}:
        return HELP
    if kind == "list":
        rows = list_clara_jobs()
        if not rows:
            return "No Clara-stage jobs yet. Run Clara after Leo, then /clara."
        lines = ["Clara jobs:"]
        for row in rows:
            lines.append(
                f"#{row['id']} {row['company_name']} — {row['job_title']} "
                f"[{application_status_label(row.get('application_status'))}]"
            )
        lines.append("Tap a job: /clara <id>")
        return "\n".join(lines)
    job_id = int(cmd["job_id"])
    if kind == "show":
        job = get_clara_job(job_id)
        if not job:
            return f"Job #{job_id} not found."
        extra = cmd.get("error")
        try:
            from .telegram_job_detail import format_job_telegram_detail
        except ImportError:
            from telegram_job_detail import format_job_telegram_detail
        body = format_job_telegram_detail(job)
        if extra:
            return f"{body}\n\n{extra}\n{HELP}"
        return body
    try:
        if kind == "status":
            job = apply_application_follow_up(
                job_id, application_status=str(cmd.get("status") or "")
            )
        elif kind == "note":
            note = str(cmd.get("note") or "")
            if not note:
                return "Usage: /note 110 your comment"
            job = apply_application_follow_up(job_id, application_note=note)
        elif kind == "employer":
            note = str(cmd.get("note") or "")
            if not note:
                return "Usage: /employer 110 what they said"
            job = apply_application_follow_up(job_id, employer_update_note=note)
        else:
            return HELP
    except ValueError as exc:
        return str(exc)
    try:
        from .telegram_job_detail import format_job_telegram_detail
    except ImportError:
        from telegram_job_detail import format_job_telegram_detail
    return format_job_telegram_detail(job, heading="Clara updated")


def _allowed_chat(chat_id: object) -> bool:
    want = (_chat_id() or "").strip()
    return bool(want) and str(chat_id) == want


def _answer_callback(query_id: str, text: str) -> None:
    token = _bot_token()
    if not token or not query_id:
        return
    try:
        httpx.post(
            f"{API_BASE}{token}/answerCallbackQuery",
            json={"callback_query_id": query_id, "text": text[:180]},
            timeout=10.0,
        )
    except Exception:
        return


def process_update(payload: dict) -> None:
    """Handle one getUpdates item."""
    cb = payload.get("callback_query")
    if isinstance(cb, dict):
        msg = cb.get("message") or {}
        chat = (msg.get("chat") or {}).get("id")
        if not _allowed_chat(chat):
            return
        data = str(cb.get("data") or "")
        qid = str(cb.get("id") or "")
        apply_m = _APPLY_CB.match(data)
        if apply_m:
            try:
                from apply_overview import handle_apply_nav
            except ImportError:
                from .apply_overview import handle_apply_nav
            try:
                toast = handle_apply_nav(
                    apply_m.group(1),
                    apply_m.group(2),
                    chat,
                    msg.get("message_id"),
                )
            except Exception as exc:
                toast = f"Apply button failed: {exc}"
            _answer_callback(qid, toast[:180])
            return
        m = _CB.match(data)
        if not m:
            _answer_callback(qid, "Unknown button")
            return
        job_id = int(m.group(1))
        status = normalize_application_status(m.group(2))
        reply = handle_parsed({"kind": "status", "job_id": job_id, "status": status})
        _answer_callback(qid, reply[:180])
        _reply(reply, job_id)
        return
    message = payload.get("message") or payload.get("edited_message")
    if not isinstance(message, dict):
        return
    chat = (message.get("chat") or {}).get("id")
    if not _allowed_chat(chat):
        return
    text = str(message.get("text") or "")
    cmd = parse_clara_text(text)
    if cmd.get("kind") in {"empty", "unknown"} and rex_await_active():
        urls = urls_from_message(message)
        if urls:
            cmd = {"kind": "rex_ingest", "job_url": urls[0]}
        else:
            cmd = {"kind": "rex_await"}
    elif cmd.get("kind") == "rex_ingest":
        urls = urls_from_message(message)
        if urls:
            cmd["job_url"] = urls[0]
    elif cmd.get("kind") not in {"empty", "unknown"}:
        clear_rex_await()
    if cmd.get("kind") == "apply_overview":
        try:
            from apply_overview import send_apply_overview
        except ImportError:
            from .apply_overview import send_apply_overview
        result = send_apply_overview()
        if not result.get("ok"):
            _reply(result.get("error") or "Could not send Apply overview.")
        return
    reply = handle_parsed(cmd)
    job_id = cmd.get("job_id") if cmd.get("kind") in {"show", "status", "note", "employer"} else None
    if cmd.get("kind") == "status":
        job_id = cmd.get("job_id")
    _reply(reply, int(job_id) if job_id else None)


def _read_offset() -> int:
    try:
        return int(OFFSET_PATH.read_text(encoding="utf-8").strip() or "0")
    except Exception:
        return 0


def _write_offset(value: int) -> None:
    try:
        OFFSET_PATH.parent.mkdir(parents=True, exist_ok=True)
        OFFSET_PATH.write_text(str(int(value)), encoding="utf-8")
    except Exception:
        return


def _poll_loop() -> None:
    token = _bot_token()
    if not token or not _chat_id():
        return
    offset = _read_offset()
    while not _stop.is_set():
        try:
            response = httpx.post(
                f"{API_BASE}{token}/getUpdates",
                json={
                    "timeout": 25,
                    "offset": offset,
                    "allowed_updates": ["message", "callback_query", "edited_message"],
                },
                timeout=35.0,
            )
            body = response.json() if response.content else {}
            if not body.get("ok"):
                time.sleep(3)
                continue
            for item in body.get("result") or []:
                uid = int(item.get("update_id") or 0)
                offset = uid + 1
                _write_offset(offset)
                try:
                    process_update(item)
                except Exception:
                    pass
        except Exception:
            time.sleep(3)


def start_clara_inbox() -> None:
    """Background getUpdates thread — no-op if Telegram env is missing."""
    global _thread
    if not _bot_token() or not _chat_id():
        return
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_poll_loop, name="telegram-clara-inbox", daemon=True)
    _thread.start()


def stop_clara_inbox() -> None:
    _stop.set()


def last_send_error() -> str:
    return LAST_SEND_ERROR
