"""Telegram Bot notifier — sends pipeline progress messages via Bot API.

Uses httpx to call the Telegram Bot API directly (no python-telegram-bot
dependency needed). Each notification includes token usage metrics
(prompt_tokens, completion_tokens, latency_ms) so the user can monitor
local model resource consumption.

# Ref: workspace rule — Asia/Hong_Kong ISO 8601 timestamps; no Any.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import httpx

API_BASE = "https://api.telegram.org/bot"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))


def _bot_token() -> str:
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def _chat_id() -> str:
    return (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()


LAST_SEND_ERROR = ""


def _is_configured() -> bool:
    """True if both bot token and chat ID are set (read live from env)."""
    return bool(_bot_token() and _chat_id())


def _api_description(response: httpx.Response) -> str:
    """Telegram error text only — never includes the bot token URL."""
    try:
        payload = response.json()
        return str(payload.get("description") or payload.get("ok") or response.status_code)
    except Exception:
        return f"HTTP {response.status_code}"


def _send_message(text: str, reply_markup: Optional[dict] = None) -> dict:
    """Send a message. Returns {ok, message_id, error}.

    MarkdownV2 → plain → plain without buttons.
    Telegram rejects `http://localhost` inline URL buttons (BUTTON_URL_INVALID).

    # Ref: https://core.telegram.org/bots/api#sendmessage
    """
    global LAST_SEND_ERROR
    LAST_SEND_ERROR = ""
    if not _is_configured():
        LAST_SEND_ERROR = "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing"
        return {"ok": False, "message_id": None, "error": LAST_SEND_ERROR}
    token = _bot_token()
    chat_id = _chat_id()
    url = f"{API_BASE}{token}/sendMessage"
    markup = reply_markup if reply_markup and reply_markup.get("inline_keyboard") else None
    attempts: list[dict] = [
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        },
        {
            "chat_id": chat_id,
            "text": text.replace("\\", ""),
            "disable_web_page_preview": True,
        },
        {
            "chat_id": chat_id,
            "text": text.replace("\\", ""),
            "disable_web_page_preview": True,
        },
    ]
    if markup:
        attempts[0]["reply_markup"] = markup
        attempts[1]["reply_markup"] = markup
    try:
        last_err = "sendMessage failed"
        for payload in attempts:
            r = httpx.post(url, json=payload, timeout=10.0)
            try:
                body = r.json() if r.content else {}
            except Exception:
                body = {}
            if r.status_code == 200 and body.get("ok"):
                LAST_SEND_ERROR = ""
                mid = (body.get("result") or {}).get("message_id")
                return {
                    "ok": True,
                    "message_id": int(mid) if mid is not None else None,
                    "error": "",
                }
            last_err = _api_description(r)
        LAST_SEND_ERROR = last_err
        return {"ok": False, "message_id": None, "error": last_err}
    except Exception as exc:
        LAST_SEND_ERROR = str(exc)[:240]
        return {"ok": False, "message_id": None, "error": LAST_SEND_ERROR}


def _send_raw(text: str, reply_markup: Optional[dict] = None) -> bool:
    """Send a message. MarkdownV2 → plain → plain without buttons."""
    return bool(_send_message(text, reply_markup).get("ok"))


def edit_message(
    chat_id: object,
    message_id: object,
    text: str,
    reply_markup: Optional[dict] = None,
) -> bool:
    """Replace text + keyboard on an existing bot message.

    # Ref: https://core.telegram.org/bots/api#editmessagetext
    """
    global LAST_SEND_ERROR
    LAST_SEND_ERROR = ""
    if not _is_configured():
        LAST_SEND_ERROR = "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing"
        return False
    token = _bot_token()
    url = f"{API_BASE}{token}/editMessageText"
    markup = reply_markup if reply_markup and reply_markup.get("inline_keyboard") else None
    attempts: list[dict] = [
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        },
        {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text.replace("\\", ""),
            "disable_web_page_preview": True,
        },
    ]
    if markup:
        for payload in attempts:
            payload["reply_markup"] = markup
    try:
        last_err = "editMessageText failed"
        for payload in attempts:
            r = httpx.post(url, json=payload, timeout=10.0)
            try:
                body = r.json() if r.content else {}
            except Exception:
                body = {}
            if r.status_code == 200 and body.get("ok"):
                LAST_SEND_ERROR = ""
                return True
            last_err = _api_description(r)
            if "message is not modified" in last_err.lower():
                LAST_SEND_ERROR = ""
                return True
        LAST_SEND_ERROR = last_err
        return False
    except Exception as exc:
        LAST_SEND_ERROR = str(exc)[:240]
        return False


def resolve_person_tag(explicit: Optional[str] = None) -> str:
    """Dashboard people.tag for Telegram. Never default/master.

    # Ref: people.tag — master identity can change
    """
    candidates = [
        explicit,
        os.environ.get("JOBHUNTER_PERSON_TAG"),
        os.environ.get("JOBHUNTER_CANDIDATE_ID"),
    ]
    for raw in candidates:
        text = str(raw or "").strip()
        if text and text.lower() not in {"default", "master"}:
            return text
    try:
        from people_store import resolve_person

        db = _PROJECT_ROOT / "job_agent.db"
        if not db.is_file():
            return ""
        conn = sqlite3.connect(str(db), timeout=5)
        try:
            person = resolve_person(conn, explicit or "default")
        finally:
            conn.close()
        if person and person.tag.lower() not in {"default", "master"}:
            return person.tag
    except Exception:
        return ""
    return ""


def _person_header(tag: Optional[str] = None) -> str:
    person = resolve_person_tag(tag)
    if not person:
        return ""
    return f"👤 *Person:* {_escape_md(person)}"


def _with_person(text: str, tag: Optional[str] = None) -> str:
    header = _person_header(tag)
    if not header:
        return text
    return header + "\n" + text


def _escape_md(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    special = "_*[]()~`>#+-=|{}.!"
    for ch in special:
        text = text.replace(ch, f"\\{ch}")
    return text


def _format_token_usage(metrics: Optional[dict]) -> str:
    """Format token usage metrics for inclusion in notifications."""
    if not metrics:
        return ""
    prompt = metrics.get("prompt_tokens", 0)
    completion = metrics.get("completion_tokens", 0)
    total = prompt + completion
    latency = metrics.get("latency_ms", 0)
    if total == 0 and latency == 0:
        return ""
    return f"\n📊 Tokens: {total} (prompt {prompt} + completion {completion}) | {latency}ms"


def _dashboard_button() -> Optional[dict]:
    """Inline keyboard only when DASHBOARD_PUBLIC_URL is a public https URL.

    # Ref: Telegram url buttons cannot be http://localhost
    """
    dash = (os.environ.get("DASHBOARD_PUBLIC_URL") or "").strip()
    if not dash.startswith("https://"):
        return None
    return {
        "inline_keyboard": [[
            {"text": "View Dashboard", "url": dash},
        ]]
    }


def send_agent_update(
    agent_name: str,
    agent_emoji: str,
    summary: str,
    details: list[str] = None,
    token_metrics: Optional[dict] = None,
    errors: list[str] = None,
    person_tag: Optional[str] = None,
) -> bool:
    """Send a formatted agent completion notification.

    Args:
        agent_name: e.g. "Rex", "Dana"
        agent_emoji: e.g. "🔍", "📋"
        summary: one-line summary e.g. "3 new jobs found"
        details: optional bullet points
        token_metrics: {prompt_tokens, completion_tokens, latency_ms}
        errors: optional error messages

    Returns True if sent (or skipped gracefully).
    """
    if not _is_configured():
        return False

    lines = [
        part for part in [_person_header(person_tag)] if part
    ] + [f"{agent_emoji} *{agent_name}* — {_escape_md(summary)}"]

    if details:
        for d in details[:8]:
            lines.append(f"  • {_escape_md(d)}")

    if errors:
        for e in errors[:3]:
            lines.append(f"  ⚠️ {_escape_md(e)}")

    usage = _format_token_usage(token_metrics)
    if usage:
        lines.append(_escape_md(usage))

    text = "\n".join(lines)
    return _send_raw(text, _dashboard_button())


def clara_status_keyboard(job_id: int) -> dict:
    """Inline buttons to set Clara application_status from Telegram."""
    from application_followup import application_status_icon

    labels = (
        ("APPLIED", f"{application_status_icon('APPLIED')} Applied"),
        ("AWAITING", f"{application_status_icon('AWAITING')} Await"),
        ("INTERVIEW", f"{application_status_icon('INTERVIEW')} Interview"),
        ("OFFER", f"{application_status_icon('OFFER')} Offer"),
        ("REJECTED", f"{application_status_icon('REJECTED')} Reject"),
        ("WITHDRAWN", f"{application_status_icon('WITHDRAWN')} Withdraw"),
    )
    rows: list[list[dict]] = []
    chunk: list[dict] = []
    for code, label in labels:
        chunk.append({"text": label, "callback_data": f"c:{int(job_id)}:{code}"})
        if len(chunk) == 3:
            rows.append(chunk)
            chunk = []
    if chunk:
        rows.append(chunk)
    dash = _dashboard_button()
    if dash:
        rows.extend(dash["inline_keyboard"])
    return {"inline_keyboard": rows}


def send_job_update(
    agent_name: str,
    event: str,
    *,
    company: str = "",
    title: str = "",
    score: Optional[int] = None,
    url: str = "",
    extra: str = "",
    person_tag: Optional[str] = None,
    job_id: Optional[int] = None,
    matched: Optional[list[str]] = None,
    gaps: Optional[list[str]] = None,
    hard: Optional[int] = None,
    transfer: Optional[int] = None,
    suitable: Optional[bool] = None,
    recommendation_reason: str = "",
    career_advisory_note: str = "",
    application_status: str = "",
) -> bool:
    """Notify when a single job row is created or updated.

    # Ref: user requirement — Telegram on each job update
    """
    if not _is_configured():
        return False
    bits = [part for part in [_person_header(person_tag)] if part]
    rich = bool(
        matched
        or gaps
        or suitable is not None
        or hard is not None
        or transfer is not None
        or recommendation_reason
    )
    if rich:
        try:
            from .telegram_job_detail import format_job_telegram_detail
        except ImportError:
            from telegram_job_detail import format_job_telegram_detail
        card = format_job_telegram_detail(
            {
                "id": job_id,
                "company_name": company,
                "job_title": title,
                "match_score": score,
                "hard_skill_match_score": hard,
                "transferability_score": transfer,
                "matched_skills": matched or [],
                "missing_skills": gaps or [],
                "job_url": url,
                "suitable": suitable,
                "recommendation_reason": recommendation_reason,
                "career_advisory_note": career_advisory_note,
                "application_status": application_status or "READY",
            },
            heading=f"{agent_name} — {event}",
        )
        bits.append(card)
    else:
        bits.append(f"📬 *{_escape_md(agent_name)}* — {_escape_md(event)}")
        if company or title:
            bits.append(
                f"*{_escape_md(company or 'Employer')}* — {_escape_md(title or 'Role')}"
            )
        if score is not None:
            bits.append(_escape_md(f"Score: {score}"))
        if extra:
            bits.append(_escape_md(extra[:280]))
        if url:
            bits.append(_escape_md(url[:300]))
    markup = clara_status_keyboard(int(job_id)) if job_id is not None else _dashboard_button()
    body = "\n".join(bits)
    if rich:
        return _send_raw(_escape_md(body), markup)
    return _send_raw(body, markup)


def send_listing_sweep(
    *,
    checked: int,
    expired: int,
    unknown: int = 0,
    items: Optional[list[dict]] = None,
    person_tag: Optional[str] = None,
) -> bool:
    """One Telegram message: how many listings were checked and which expired.

    # Ref: pre-Rex kanban URL sweep
    """
    if not _is_configured():
        return False
    rows = items or []
    lines = [part for part in [_person_header(person_tag)] if part]
    lines.append("🔗 *Listing check* — before Rex")
    lines.append(_escape_md(f"Checked: {checked} active kanban jobs"))
    lines.append(_escape_md(f"Marked expired: {expired}"))
    if unknown:
        lines.append(_escape_md(f"Unreachable (not expired): {unknown}"))
    if rows:
        lines.append(_escape_md("Expired checklist:"))
        used = len("\n".join(lines))
        omitted = 0
        for row in rows:
            job_id = row.get("id", "?")
            company = str(row.get("company") or "Employer")[:40]
            title = str(row.get("title") or "Role")[:50]
            reason = str(row.get("reason") or "")[:80]
            bullet = f"  • #{job_id} {company} — {title} ({reason})"
            candidate = _escape_md(bullet)
            if used + len(candidate) + 40 > 3500:
                omitted += 1
                continue
            lines.append(candidate)
            used += len(candidate) + 1
        if omitted:
            lines.append(_escape_md(f"  … and {omitted} more"))
    else:
        lines.append(_escape_md("Expired checklist: none"))
    return _send_raw("\n".join(lines), _dashboard_button())


def send_pipeline_summary(
    jobs_found: int,
    dossiers: int,
    cv_generated: int,
    application_ready: int,
    total_tokens: int = 0,
    total_latency_ms: int = 0,
    errors: list[str] = None,
    person_tag: Optional[str] = None,
) -> bool:
    """Send a final pipeline summary with funnel stats."""
    if not _is_configured():
        return False

    lines = [part for part in [_person_header(person_tag)] if part] + [
        "🏭 *Pipeline Complete*",
        _escape_md(f"  Found: {jobs_found}"),
        _escape_md(f"  Vetted: {dossiers}"),
        _escape_md(f"  CVs: {cv_generated}"),
        _escape_md(f"  Application Ready: {application_ready}"),
    ]

    if total_tokens > 0:
        lines.append(_escape_md(f"  Total tokens: {total_tokens} | {total_latency_ms}ms"))

    if errors:
        lines.append(_escape_md(f"  Errors: {len(errors)}"))

    text = "\n".join(lines)
    return _send_raw(text, _dashboard_button())


def send_error(agent_name: str, error: str, person_tag: Optional[str] = None) -> bool:
    """Send an error alert."""
    if not _is_configured():
        return False
    text = _with_person(
        f"❌ *{agent_name}* ERROR\n{_escape_md(error[:500])}",
        person_tag,
    )
    return _send_raw(text, _dashboard_button())


def send_document(filepath: str, caption: str = "") -> bool:
    """Send a file (PDF, markdown, etc.) to the configured Telegram chat.

    Uses the Telegram Bot API sendDocument method with multipart/form-data.
    Returns True on success, False if not configured or the upload fails.

    # Ref: https://core.telegram.org/bots/api#senddocument
    """
    global LAST_SEND_ERROR
    LAST_SEND_ERROR = ""
    if not _is_configured():
        LAST_SEND_ERROR = "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing"
        return False
    from pathlib import Path
    p = Path(filepath)
    if not p.is_file():
        LAST_SEND_ERROR = f"file not found: {filepath}"
        return False
    token = _bot_token()
    chat_id = _chat_id()
    url = f"{API_BASE}{token}/sendDocument"
    try:
        with p.open("rb") as fh:
            files = {"document": (p.name, fh, "application/octet-stream")}
            data: dict[str, object] = {"chat_id": chat_id}
            if caption:
                person = resolve_person_tag()
                if person and not caption.startswith("👤"):
                    caption = f"👤 {person}\n{caption}"
                data["caption"] = caption[:1024]
            r = httpx.post(url, data=data, files=files, timeout=60.0)
        body = r.json() if r.content else {}
        if r.status_code == 200 and body.get("ok"):
            return True
        LAST_SEND_ERROR = _api_description(r)
        return False
    except Exception as exc:
        LAST_SEND_ERROR = str(exc)[:240]
        return False


def send_job_documents(
    cv_pdf_path: str = "",
    checklist_path: str = "",
    dossier_path: str = "",
    cover_letter_path: str = "",
    company: str = "",
    title: str = "",
    person_tag: Optional[str] = None,
) -> dict:
    """Send all available job documents to Telegram. Returns a summary dict.

    Sends: CV, cover letter, application checklist, company dossier.
    # Ref: user requirement — send all Leo's documents + dossier + checklist
    """
    results: list[dict] = []
    sent = 0
    failed = 0
    skipped = 0
    label = f"{company or 'Employer'} — {title or 'Role'}" if company or title else ""

    for doc_path, doc_label in [
        (cv_pdf_path, "CV"),
        (cover_letter_path, "Cover Letter"),
        (checklist_path, "Application Checklist"),
        (dossier_path, "Company Dossier"),
    ]:
        if not doc_path:
            skipped += 1
            continue
        from pathlib import Path
        if not Path(doc_path).is_file():
            results.append({"document": doc_label, "ok": False, "error": "file not found"})
            failed += 1
            continue
        person = resolve_person_tag(person_tag)
        caption = f"📄 {doc_label}" + (f" — {label}" if label else "")
        if person:
            caption = f"👤 {person}\n{caption}"
        ok = send_document(doc_path, caption=caption)
        results.append({"document": doc_label, "ok": ok, "error": LAST_SEND_ERROR if not ok else ""})
        if ok:
            sent += 1
        else:
            failed += 1

    return {
        "sent": sent,
        "failed": failed,
        "skipped": skipped,
        "details": results,
        "configured": _is_configured(),
    }


def send_linkedin_mcp_status(person_tag: Optional[str] = None) -> bool:
    """Tell Telegram where LinkedIn MCP is attached and how Jobhunter uses it."""
    if not _is_configured():
        return False
    try:
        from linkedin_mcp_client import mcp_status_lines
    except Exception:
        return False
    body = "\n".join(_escape_md(line) for line in mcp_status_lines())
    text = _with_person(f"🔗 *LinkedIn MCP*\n{body}", person_tag)
    return _send_raw(text, _dashboard_button())


def send_startup() -> bool:
    """Send a startup message when the scheduler starts."""
    if not _is_configured():
        return False
    hours = os.environ.get("SCHEDULER_HOURS", "9,18")
    tag = resolve_person_tag()
    lines = [part for part in [_person_header(tag)] if part]
    lines.append(_escape_md(f"Jobhunter scheduler started. Schedule: {hours} HKT"))
    try:
        from linkedin_mcp_client import mcp_status_lines

        lines.append(_escape_md("LinkedIn MCP:"))
        lines.extend(_escape_md(line) for line in mcp_status_lines()[:5])
    except Exception:
        pass
    return _send_raw("\n".join(lines))


_bot_info_cache: Optional[dict[str, object]] = None


def get_bot_info() -> dict[str, object]:
    """Return public bot identity (username / id / t.me link). Token never included.

    Username comes from TELEGRAM_BOT_USERNAME if set, else Telegram getMe.
    # Ref: https://core.telegram.org/bots/api#getme
    """
    global _bot_info_cache
    if _bot_info_cache is not None:
        return _bot_info_cache

    username_env = os.environ.get("TELEGRAM_BOT_USERNAME", "").strip().lstrip("@")
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    username = username_env or None
    bot_id: Optional[int] = None
    first_name: Optional[str] = None

    if token:
        try:
            r = httpx.get(f"{API_BASE}{token}/getMe", timeout=8.0)
            payload = r.json()
            if r.status_code == 200 and payload.get("ok"):
                result = payload.get("result") or {}
                username = username or (result.get("username") or None)
                raw_id = result.get("id")
                bot_id = int(raw_id) if raw_id is not None else None
                first_name = result.get("first_name") or None
        except Exception:
            pass

    tme_url = f"https://t.me/{username}" if username else None
    tg_url = f"tg://resolve?domain={username}" if username else None
    info = {
        "configured": bool(token),
        "username": username,
        "bot_id": bot_id,
        "first_name": first_name,
        "tme_url": tme_url,
        "tg_url": tg_url,
    }
    if username:
        _bot_info_cache = info
    return info
