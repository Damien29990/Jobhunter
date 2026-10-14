"""Apply-column Telegram overview: prev/next pages, 2-hour session.

Buttons only work while FastAPI hosts the Telegram inbox poller.

# Ref: telegram_inbox callback_query · Asia/Hong_Kong
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

HK_TZ = timezone(timedelta(hours=8))
SESSION_TTL = timedelta(hours=2)
MAX_JOBS = 80
LIST_PAGE_SIZE = 8
LIST_BUTTONS_PER_ROW = 4
LIST_SEP = "━━━━━━━━━━━━━━━━━━"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "job_agent.db"
SESSION_PATH = PROJECT_ROOT / "output" / "apply_overview_sessions.json"
FINISH_SNAPSHOT_PATH = PROJECT_ROOT / "output" / "telemetry" / "pipeline_last_finish.json"

_lock = threading.Lock()


def _tg():
    """telegram_notifier as package or flat src/api path.

    # Ref: uvicorn src.api.server — relative import required
    """
    try:
        from . import telegram_notifier as tg
    except ImportError:
        import telegram_notifier as tg  # type: ignore
    return tg


class ApplySession(BaseModel):
    """In-memory Apply overview session. # Ref: 2h HKT expiry"""

    id: str
    chat_id: str
    message_id: Optional[int] = None
    created_at: str
    expires_at: str
    job_ids: list[int] = Field(default_factory=list)
    index: int = 0


def now_hk() -> datetime:
    return datetime.now(HK_TZ)


def session_expired(session: ApplySession, at: Optional[datetime] = None) -> bool:
    """True when the 2-hour window has passed.

    # Ref: user — expire time like 2 hours
    """
    stamp = at or now_hk()
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=HK_TZ)
    try:
        expires = datetime.fromisoformat(session.expires_at)
    except ValueError:
        return True
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=HK_TZ)
    return stamp >= expires


def list_page_count(n_jobs: int) -> int:
    """How many compact list pages for n Apply jobs."""
    if int(n_jobs) <= 0:
        return 1
    return (int(n_jobs) + LIST_PAGE_SIZE - 1) // LIST_PAGE_SIZE


def page_count(session: ApplySession) -> int:
    n = len(session.job_ids)
    return list_page_count(n) + n


def page_kind(session: ApplySession) -> tuple[str, int]:
    """('list', list_page) or ('card', job_index)."""
    lists = list_page_count(len(session.job_ids))
    idx = int(session.index)
    if idx < lists:
        return ("list", idx)
    return ("card", idx - lists)


def step_session(session: ApplySession, delta: int) -> ApplySession:
    """Move prev (-1) or next (+1), wrapping list pages ↔ job cards."""
    n = page_count(session)
    if n <= 0:
        return session
    session.index = (int(session.index) + int(delta)) % n
    return session


def apply_nav_keyboard(session_id: str) -> dict:
    """Previous / next only — used on the overview page."""
    sid = str(session_id)
    return {
        "inline_keyboard": [
            [
                {"text": "◀️ Previous", "callback_data": f"a:{sid}:p"},
                {"text": "Next ▶️", "callback_data": f"a:{sid}:n"},
            ]
        ]
    }


def apply_list_nav_keyboard(session_id: str, page: int, pages: int) -> dict:
    """List footer nav: Previous · Page N/M · Next.

    # Ref: Telegram_Job_List_Template.md — Recommended Inline Keyboard
    """
    sid = str(session_id)
    shown = max(1, int(page))
    total = max(1, int(pages))
    return {
        "inline_keyboard": [
            [
                {"text": "◀️ Previous", "callback_data": f"a:{sid}:p"},
                {"text": f"Page {shown}/{total}", "callback_data": f"a:{sid}:x"},
                {"text": "Next ▶️", "callback_data": f"a:{sid}:n"},
            ]
        ]
    }


def _http_url(raw: object) -> str:
    text = str(raw or "").strip()
    if text.startswith("https://") or text.startswith("http://"):
        return text
    return ""


def _button_url(raw: object) -> str:
    """Telegram url buttons: https only. http://localhost is rejected."""
    text = _http_url(raw)
    return text if text.startswith("https://") else ""


def _existing_file(*candidates: object) -> str:
    for raw in candidates:
        path = Path(str(raw or ""))
        if str(raw or "").strip() and path.is_file():
            return str(path)
    return ""


def apply_job_keyboard(session_id: str, job: Optional[dict] = None) -> dict:
    """Compact card actions + prev/next.

    # Ref: Telegram_Job_Card_Template.md — Suggested Inline Keyboard
    """
    sid = str(session_id)
    rows: list[list[dict]] = []
    if job:
        job_id = int(job.get("id") or 0)
        url = _button_url(job.get("job_url"))
        has_cv = bool(
            _existing_file(job.get("cv_pdf_path"), job.get("cv_typ_path"))
        )
        has_letter = bool(
            _existing_file(
                job.get("cover_letter_pdf_path"), job.get("cover_letter_typ_path")
            )
        )
        top: list[dict] = []
        if url:
            top.append({"text": "🔗 View Job", "url": url})
        if has_cv:
            top.append({"text": "📄 View CV", "callback_data": f"a:{sid}:cv"})
        if top:
            rows.append(top)
        if has_letter:
            rows.append(
                [{"text": "✉️ View Cover Letter", "callback_data": f"a:{sid}:cl"}]
            )
        if job_id:
            rows.append(
                [
                    {"text": "✅ Mark Applied", "callback_data": f"c:{job_id}:APPLIED"},
                    {"text": "📝 Edit Details", "callback_data": f"a:{sid}:ed"},
                ]
            )
    rows.append(
        [
            {"text": "◀️ Previous", "callback_data": f"a:{sid}:p"},
            {"text": "📋 List", "callback_data": f"a:{sid}:l"},
            {"text": "Next ▶️", "callback_data": f"a:{sid}:n"},
        ]
    )
    return {"inline_keyboard": rows}


def list_job_button_label(page_slot: int, score: object = None) -> str:
    """Page-local key 01–08. Score stays in the list body.

    # Ref: Telegram_Job_List_Template.md — 01–08 primary button keys
    """
    del score
    return f"{max(1, int(page_slot)):02d}"


def list_status_label(raw: object) -> str:
    """READY / AWAITING / APPLIED (plus later Clara states).

    # Ref: Telegram_Job_List_Template.md — Status Display
    """
    key = str(raw or "READY").strip().upper().replace("-", "_").replace(" ", "_")
    marks = {
        "READY": "🟢 READY",
        "AWAITING": "🟡 AWAITING",
        "APPLIED": "✅ APPLIED",
        "EMPLOYER_UPDATE": "📬 EMPLOYER UPDATE",
        "INTERVIEW": "🎤 INTERVIEW",
        "OFFER": "🎉 OFFER",
        "REJECTED": "🔴 REJECTED",
        "WITHDRAWN": "⚪ WITHDRAWN",
    }
    return marks.get(key, f"⚪ {key or 'READY'}")


def _skill_tags(raw: object) -> str:
    """Up to 3 matched skills as `Tag 1 / Tag 2`.

    # Ref: Telegram_Job_List_Template.md — important job tags
    """
    names: list[str] = []
    if isinstance(raw, list):
        names = [str(item).strip() for item in raw if str(item).strip()]
    elif isinstance(raw, str) and raw.strip():
        text = raw.strip()
        parsed: object = None
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        if isinstance(parsed, list):
            names = [str(item).strip() for item in parsed if str(item).strip()]
        else:
            sep = "/" if "/" in text else ","
            names = [part.strip() for part in text.split(sep) if part.strip()]
    short = [name for name in names if _is_short_tag(name)]
    return " / ".join(short[:3])


def _is_short_tag(name: str) -> bool:
    """True for compact skill chips, not Dana narrative bullets."""
    if not (1 <= len(name) <= 32):
        return False
    if ". " in name or "!" in name or "?" in name or ";" in name:
        return False
    return len(name.split()) <= 5


def apply_list_keyboard(session: ApplySession, jobs: Optional[list[dict]] = None) -> dict:
    """Number buttons for jobs on this list page — tap opens that card."""
    kind, pos = page_kind(session)
    if kind != "list":
        return apply_nav_keyboard(session.id)
    start = pos * LIST_PAGE_SIZE
    chunk = session.job_ids[start:start + LIST_PAGE_SIZE]
    sid = session.id
    pages = list_page_count(len(session.job_ids))
    rows: list[list[dict]] = []
    row: list[dict] = []
    for offset, _jid in enumerate(chunk):
        label = list_job_button_label(offset + 1)
        data = f"a:{sid}:j{start + offset}"
        row.append({"text": label, "callback_data": data})
        if len(row) == LIST_BUTTONS_PER_ROW:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.extend(apply_list_nav_keyboard(sid, pos + 1, pages)["inline_keyboard"])
    return {"inline_keyboard": rows}


def apply_page_keyboard(session: ApplySession, jobs: Optional[list[dict]] = None) -> dict:
    """List pages → numbered job buttons. Job card → compact action keyboard."""
    kind, pos = page_kind(session)
    if kind == "list":
        return apply_list_keyboard(session, jobs)
    rows = jobs if jobs is not None else list_apply_jobs()
    jid = session.job_ids[pos]
    return apply_job_keyboard(session.id, _job_by_id(jid, rows) or {"id": jid})


def _load_store() -> dict[str, ApplySession]:
    if not SESSION_PATH.is_file():
        return {}
    try:
        raw = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, ApplySession] = {}
    for sid, data in raw.items():
        try:
            session = ApplySession.model_validate(data)
        except Exception:
            continue
        if session_expired(session):
            continue
        out[str(sid)] = session
    return out


def _save_store(store: dict[str, ApplySession]) -> None:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {sid: sess.model_dump() for sid, sess in store.items()}
    SESSION_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_session(session_id: str) -> Optional[ApplySession]:
    with _lock:
        return _load_store().get(session_id)


def put_session(session: ApplySession) -> None:
    with _lock:
        store = _load_store()
        store[session.id] = session
        _save_store(store)


def clear_sessions() -> None:
    with _lock:
        _save_store({})


def create_session(job_ids: list[int], chat_id: str = "") -> ApplySession:
    created = now_hk()
    sid = uuid.uuid4().hex[:8]
    session = ApplySession(
        id=sid,
        chat_id=str(chat_id or ""),
        created_at=created.isoformat(timespec="seconds"),
        expires_at=(created + SESSION_TTL).isoformat(timespec="seconds"),
        job_ids=[int(i) for i in job_ids],
        index=0,
    )
    put_session(session)
    return session


def list_apply_jobs(limit: int = MAX_JOBS) -> list[dict]:
    """Kanban Apply jobs: application_ready, not expired.

    # Ref: job_postings.application_ready
    """
    if not DB_PATH.is_file():
        return []
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT j.id, j.company_name, j.job_title, j.match_score,
                   j.hard_skill_match_score, j.transferability_score,
                   j.location_mode, j.salary_range, j.job_url, j.cv_status,
                   j.application_status, j.source_domain, j.target_industry,
                   j.matched_skills,
                   j.cv_pdf_path, j.cv_typ_path,
                   {letter_cols}
                   d.vetting_verdict, d.confidence AS dossier_confidence
            FROM job_postings j
            LEFT JOIN company_dossiers d
              ON LOWER(TRIM(j.company_name)) = LOWER(TRIM(d.company_name))
            WHERE COALESCE(j.application_ready, 0) = 1
              AND COALESCE(j.expired, 0) = 0
            ORDER BY COALESCE(j.match_score, 0) DESC, j.id DESC
            LIMIT ?
        """
        params = (max(1, min(80, int(limit))),)
        try:
            rows = conn.execute(
                sql.format(
                    letter_cols="j.cover_letter_pdf_path, j.cover_letter_typ_path,"
                ),
                params,
            ).fetchall()
        except sqlite3.OperationalError:
            rows = conn.execute(
                sql.format(letter_cols=""),
                params,
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _job_by_id(job_id: int, jobs: list[dict]) -> Optional[dict]:
    for row in jobs:
        if int(row["id"]) == int(job_id):
            return row
    return None


def _candidate_name() -> str:
    try:
        return _tg().resolve_person_tag() or "Candidate"
    except Exception:
        return "Candidate"


def _blank(value: object, empty: str) -> str:
    text = str(value or "").strip()
    if not text or text.lower() in {"not specified", "not disclosed", "n/a", "none", "-"}:
        return empty
    return text


def _cv_label(raw: object) -> str:
    key = str(raw or "").strip().upper()
    labels = {
        "MATERIALS_GENERATED": "Materials generated",
        "MATERIALS_RENDERED": "Materials rendered",
        "GENERATION_FAILED": "Generation failed",
    }
    return labels.get(key, str(raw or "").strip() or "Not specified")


def _score(value: object) -> str:
    if value is None or value == "":
        return "?"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def _verdict_line(verdict: object, confidence: object) -> str:
    raw = str(verdict or "").strip().upper()
    if not raw:
        return ""
    mark = "🟢" if raw == "PROCEED" else "🔴" if raw == "AVOID" else "⚪"
    line = f"🤖 Agent: {mark} {raw}"
    if confidence is not None and str(confidence).strip() != "":
        line += f"\nConfidence: {_score(confidence)} / 100"
    return line


def render_apply_page(session: ApplySession, jobs: Optional[list[dict]] = None) -> str:
    """List pages follow Job List template; cards stay compact.

    # Ref: Telegram_Job_List_Template.md · Telegram_Job_Card_Template.md
    """
    rows = jobs if jobs is not None else list_apply_jobs()
    by_id = {int(r["id"]): r for r in rows}
    until = session.expires_at[11:16] if len(session.expires_at) >= 16 else session.expires_at
    n_jobs = len(session.job_ids)
    person = _candidate_name()
    kind, pos = page_kind(session)
    if kind == "list":
        lists = list_page_count(n_jobs)
        start = pos * LIST_PAGE_SIZE
        chunk = session.job_ids[start:start + LIST_PAGE_SIZE]
        shown_from = start + 1 if n_jobs else 0
        shown_to = start + len(chunk)
        found = f"{n_jobs} job{'s' if n_jobs != 1 else ''} found"
        lines = [
            f"👤 {person}",
            f"📋 {found}  ·  Page {pos + 1} of {lists}",
            f"📄 Showing {shown_from}–{shown_to}",
            f"⏳ Expires {until} HKT  ·  Session: `{session.id}`",
            "",
            LIST_SEP,
            "",
        ]
        if not chunk:
            lines.append("No Apply jobs yet.")
            return "\n".join(lines)
        for offset, jid in enumerate(chunk):
            slot = list_job_button_label(offset + 1)
            job = by_id.get(jid)
            if not job:
                lines.append(f"{slot} · `#{jid}`")
                lines.append("(missing)")
                lines.append("")
                continue
            company = str(job.get("company_name") or "Employer")
            title = str(job.get("job_title") or "Role")
            lines.append(f"{slot} · `#{jid}`")
            lines.append(f"💼 {title}")
            lines.append(f"🏢 {company}")
            place = _blank(job.get("location_mode"), "")
            if place:
                lines.append(f"📍 {place}")
            tags = _skill_tags(job.get("matched_skills"))
            if tags:
                lines.append(f"🏷️ {tags}")
            lines.append(
                f"🎯 {_score(job.get('match_score'))}/100  ·  "
                f"{list_status_label(job.get('application_status'))}"
            )
            lines.append("")
        lines.extend(
            [
                LIST_SEP,
                "",
                "💡 Tap a number to open the job",
                f"◀️ Previous  ·  Page {pos + 1}/{lists}  ·  Next ▶️",
            ]
        )
        return "\n".join(lines)

    jid = session.job_ids[pos]
    job = by_id.get(jid) or {"id": jid}
    company = str(job.get("company_name") or "Employer")
    title = str(job.get("job_title") or "Role")
    industry = str(job.get("target_industry") or "").strip()
    lines = [
        f"👤 {person}  ·  📊 {pos + 1}/{n_jobs}  ·  `#{jid}`",
        "",
        f"💼 {title}",
        f"🏢 {company}",
    ]
    if industry:
        lines.append(f"🌏 {industry}")
    lines.extend(
        [
            "",
            f"🎯 Match: {_score(job.get('match_score'))}/100",
            f"🧱 Hard: {_score(job.get('hard_skill_match_score'))}  ·  "
            f"🔄 Transfer: {_score(job.get('transferability_score'))}",
            "",
            f"📍 Location: {_blank(job.get('location_mode'), 'Not specified')}",
            f"💰 Salary: {_blank(job.get('salary_range'), 'Not disclosed')}",
            "",
            f"📄 CV: {_cv_label(job.get('cv_status'))}",
            f"✅ Status: {str(job.get('application_status') or 'READY')}",
        ]
    )
    agent = _verdict_line(job.get("vetting_verdict"), job.get("dossier_confidence"))
    if agent:
        lines.extend(["", agent])
    url = _http_url(job.get("job_url"))
    if url:
        lines.extend(["", f"🔗 {url}"])
    lines.extend(["", f"⏳ Session expires: {until} HKT"])
    return "\n".join(lines)


def send_apply_overview() -> dict:
    """Send a new 2-hour overview to TELEGRAM_CHAT_ID."""
    tg = _tg()
    if not tg._is_configured():
        return {"ok": False, "error": tg.LAST_SEND_ERROR or "Telegram not configured"}
    jobs = list_apply_jobs()
    session = create_session([int(j["id"]) for j in jobs], chat_id=tg._chat_id())
    text = tg._escape_md(render_apply_page(session, jobs))
    result = tg._send_message(text, apply_page_keyboard(session, jobs))
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error") or tg.LAST_SEND_ERROR}
    session.message_id = int(result["message_id"]) if result.get("message_id") else None
    put_session(session)
    return {"ok": True, "session_id": session.id, "message_id": session.message_id, "jobs": len(session.job_ids)}


class PipelineFinishSnapshot(BaseModel):
    """Last pipeline completion stamp.

    # Ref: job_postings.application_ready · Asia/Hong_Kong
    """

    finished_at: str
    success: bool = True
    error: Optional[str] = None
    source: str = "desk"
    telegram_ok: Optional[bool] = None
    application_ready: int = 0
    job_ids: list[int] = Field(default_factory=list)


def load_finish_snapshot() -> Optional[PipelineFinishSnapshot]:
    if not FINISH_SNAPSHOT_PATH.is_file():
        return None
    try:
        raw = json.loads(FINISH_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        return PipelineFinishSnapshot.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def announce_pipeline_finish(
    *,
    success: bool,
    source: str,
    error: str = "",
    send_telegram: bool = True,
) -> PipelineFinishSnapshot:
    """Persist ready-to-apply job ids and optionally send the Telegram overview.

    Called when LangGraph or desk Finish Pipeline ends, even if Clara audited 0
    new packs — the list is every current application_ready listing.
    """
    jobs = list_apply_jobs(limit=80)
    snap = PipelineFinishSnapshot(
        finished_at=now_hk().isoformat(timespec="seconds"),
        success=success,
        error=(error or None),
        source=source,
        application_ready=len(jobs),
        job_ids=[int(j["id"]) for j in jobs],
    )
    if success and send_telegram:
        try:
            telegram_result = send_apply_overview()
            snap.telegram_ok = bool(telegram_result.get("ok"))
        except Exception:
            snap.telegram_ok = False
    FINISH_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    FINISH_SNAPSHOT_PATH.write_text(
        json.dumps(snap.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return snap


def handle_apply_nav(session_id: str, action: str, chat_id: object, message_id: object) -> str:
    """Prev/next, send CV/letter, or edit hint. Returns toast text."""
    tg = _tg()

    session = get_session(session_id)
    if session is None:
        return "Apply session not found. Send /apply while the API is running."
    if session_expired(session):
        until = session.expires_at[11:16] if len(session.expires_at) >= 16 else session.expires_at
        tg.edit_message(
            chat_id,
            message_id,
            tg._escape_md(
                f"Session {session.id} expired at {until} HKT.\n"
                "Send /apply after the API is hosting for a new overview."
            ),
            reply_markup=None,
        )
        return f"Session expired at {until} HKT"

    jobs = list_apply_jobs()
    kind, pos = page_kind(session)
    job = None
    if kind == "card" and session.job_ids:
        job = _job_by_id(session.job_ids[pos], jobs)

    if action == "cv":
        path = _existing_file((job or {}).get("cv_pdf_path"), (job or {}).get("cv_typ_path"))
        if not path:
            return "No CV file for this job."
        ok = tg.send_document(path, caption=f"CV — {(job or {}).get('company_name') or ''}")
        return "CV sent" if ok else "Could not send CV"
    if action == "cl":
        path = _existing_file(
            (job or {}).get("cover_letter_pdf_path"),
            (job or {}).get("cover_letter_typ_path"),
        )
        if not path:
            return "No cover letter for this job."
        ok = tg.send_document(
            path, caption=f"Cover letter — {(job or {}).get('company_name') or ''}"
        )
        return "Cover letter sent" if ok else "Could not send cover letter"
    if action == "ed":
        job_id = int((job or {}).get("id") or 0)
        if not job_id:
            return "Open a job card first."
        tg._send_raw(
            tg._escape_md(
                f"Edit #{job_id} {(job or {}).get('company_name') or ''}\n"
                f"/note {job_id} your comment\n"
                f"/clara {job_id} APPLIED"
            ),
            tg.clara_status_keyboard(job_id),
        )
        return "Edit details"
    n_jobs = len(session.job_ids)
    lists = list_page_count(n_jobs)
    if action == "x":
        return _publish_apply_page(tg, session, jobs, chat_id, message_id)
    if action == "l":
        kind_now, pos_now = page_kind(session)
        job_i = pos_now if kind_now == "card" else 0
        session.index = min(lists - 1, job_i // LIST_PAGE_SIZE) if n_jobs else 0
        put_session(session)
        return _publish_apply_page(tg, session, jobs, chat_id, message_id)
    if action.startswith("j") and action[1:].isdigit():
        job_i = int(action[1:])
        if job_i < 0 or job_i >= n_jobs:
            return "That job is not on this list."
        session.index = lists + job_i
        put_session(session)
        return _publish_apply_page(tg, session, jobs, chat_id, message_id)
    if action not in {"p", "n"}:
        return "Unknown button"

    step_session(session, -1 if action == "p" else 1)
    put_session(session)
    return _publish_apply_page(tg, session, jobs, chat_id, message_id)


def _publish_apply_page(
    tg: object,
    session: ApplySession,
    jobs: list[dict],
    chat_id: object,
    message_id: object,
) -> str:
    text = tg._escape_md(render_apply_page(session, jobs))
    markup = apply_page_keyboard(session, jobs)
    ok = tg.edit_message(chat_id, message_id, text, markup)
    if not ok:
        fallback = tg._send_message(text, markup)
        if fallback.get("ok"):
            session.message_id = fallback.get("message_id")
            put_session(session)
            return "Opened the next page in a new message"
        return f"Could not update: {tg.LAST_SEND_ERROR or 'Telegram rejected the edit'}"
    kind, pos = page_kind(session)
    if kind == "list":
        return f"List {pos + 1}/{list_page_count(len(session.job_ids))}"
    shown = _job_by_id(session.job_ids[pos], jobs)
    label = (shown or {}).get("company_name") or f"#{session.job_ids[pos]}"
    return f"{pos + 1}/{len(session.job_ids)} {label}"
