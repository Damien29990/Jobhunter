"""Telegram Bot notifier — sends pipeline progress messages via Bot API.

Uses httpx to call the Telegram Bot API directly (no python-telegram-bot
dependency needed). Each notification includes token usage metrics
(prompt_tokens, completion_tokens, latency_ms) so the user can monitor
local model resource consumption.

# Ref: workspace rule — Asia/Hong_Kong ISO 8601 timestamps; no Any.
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

API_BASE = "https://api.telegram.org/bot"


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


def _send_raw(text: str, reply_markup: Optional[dict] = None) -> bool:
    """Send a message. MarkdownV2 → plain → plain without buttons.

    Telegram rejects `http://localhost` inline URL buttons (BUTTON_URL_INVALID),
    which previously made every job/pipeline ping look like a silent skip.

    # Ref: https://core.telegram.org/bots/api#sendmessage
    """
    global LAST_SEND_ERROR
    LAST_SEND_ERROR = ""
    if not _is_configured():
        LAST_SEND_ERROR = "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing"
        return False
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
                return True
            last_err = _api_description(r)
        LAST_SEND_ERROR = last_err
        return False
    except Exception as exc:
        LAST_SEND_ERROR = str(exc)[:240]
        return False


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

    lines = [f"{agent_emoji} *{agent_name}* — {_escape_md(summary)}"]

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


def send_job_update(
    agent_name: str,
    event: str,
    *,
    company: str = "",
    title: str = "",
    score: Optional[int] = None,
    url: str = "",
    extra: str = "",
) -> bool:
    """Notify when a single job row is created or updated.

    # Ref: user requirement — Telegram on each job update
    """
    if not _is_configured():
        return False
    bits = [f"📬 *{_escape_md(agent_name)}* — {_escape_md(event)}"]
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
    return _send_raw("\n".join(bits), _dashboard_button())


def send_pipeline_summary(
    jobs_found: int,
    dossiers: int,
    cv_generated: int,
    application_ready: int,
    total_tokens: int = 0,
    total_latency_ms: int = 0,
    errors: list[str] = None,
) -> bool:
    """Send a final pipeline summary with funnel stats."""
    if not _is_configured():
        return False

    lines = [
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


def send_error(agent_name: str, error: str) -> bool:
    """Send an error alert."""
    if not _is_configured():
        return False
    text = f"❌ *{agent_name}* ERROR\n{_escape_md(error[:500])}"
    return _send_raw(text, _dashboard_button())


def send_startup() -> bool:
    """Send a startup message when the scheduler starts."""
    if not _is_configured():
        return False
    hours = os.environ.get("SCHEDULER_HOURS", "9,18")
    text = _escape_md(f"Jobhunter scheduler started. Schedule: {hours} HKT")
    return _send_raw(text)


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
