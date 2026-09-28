"""Jobhunter-owned LinkedIn MCP client. Cursor is not used.

Milo / FastAPI spawn `uvx linkedin-api-mcp` and call get_profile. The session
cookie comes from the OS keyring or LINKEDIN_COOKIE in Jobhunter `.env`.

# Ref: POST /api/candidates/import-linkedin — MCP first, Tavily fallback
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

AGENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = AGENT_DIR.parent.parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

_VALIDATORS_DIR = Path(__file__).resolve().parent.parent / "validators"
if str(_VALIDATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS_DIR))

from contact_links import (  # noqa: E402
    LinkedInProfileRef,
    is_placeholder_profile_name,
    name_from_linkedin_handle,
)

_MCP_TOOL_CANDIDATES = (
    "get_profile",
    "get_person_profile",
    "get_linkedin_profile",
    "linkedin_get_profile",
)
_DEFAULT_MCP_ARGS = "linkedin-api-mcp"


def _load_agent_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env")


def _find_uvx() -> str:
    found = shutil.which("uvx") or ""
    if found:
        return found
    scripts = Path(sys.executable).resolve().parent / "Scripts" / "uvx.exe"
    if scripts.is_file():
        return str(scripts)
    local = (
        Path(os.environ.get("LOCALAPPDATA") or "")
        / "Programs"
        / "Python"
        / "Python312"
        / "Scripts"
        / "uvx.exe"
    )
    return str(local) if local.is_file() else ""


def _mcp_command() -> list[str]:
    """Command FastAPI/Milo uses to start the LinkedIn MCP child process."""
    _load_agent_env()
    raw = (os.environ.get("LINKEDIN_MCP_COMMAND") or "").strip() or _find_uvx()
    if not raw:
        return []
    extra = (os.environ.get("LINKEDIN_MCP_ARGS") or _DEFAULT_MCP_ARGS).strip()
    posix = os.name != "nt"
    parts = shlex.split(raw, posix=posix)
    if extra:
        parts.extend(shlex.split(extra, posix=posix))
    return parts


def _child_env() -> dict[str, str]:
    env = {str(key): str(value) for key, value in os.environ.items()}
    env.setdefault("LINKEDIN_HEADLESS", "true")
    return env


def _write_rpc(proc: subprocess.Popen[bytes], payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    assert proc.stdin is not None
    proc.stdin.write(header + body)
    proc.stdin.flush()


def _read_rpc(proc: subprocess.Popen[bytes]) -> dict:
    assert proc.stdout is not None
    headers: dict[str, str] = {}
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("LinkedIn MCP closed stdout")
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8", errors="replace").strip()
        if ":" not in decoded:
            continue
        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length") or "0")
    raw = proc.stdout.read(length) if length else b"{}"
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("LinkedIn MCP returned a non-object")
    return data


def _parse_json_object(text: str) -> Optional[dict]:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _as_list(raw: object) -> list:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("elements", "values", "items", "positions", "data"):
            inner = raw.get(key)
            if isinstance(inner, list):
                return inner
    return []


def _looks_like_profile(data: dict) -> bool:
    return bool(
        data.get("name")
        or data.get("public_id")
        or data.get("headline")
        or data.get("experience")
        or data.get("firstName")
        or data.get("fullName")
    )


def _unwrap_tool_result(payload: dict) -> Optional[dict]:
    if payload.get("error"):
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    if result.get("isError"):
        return None
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        if _looks_like_profile(structured):
            return structured
        for key in ("profile", "data", "person", "result"):
            inner = structured.get(key)
            if isinstance(inner, dict) and _looks_like_profile(inner):
                return inner
    contents = result.get("content")
    if isinstance(contents, list):
        for item in contents:
            if not isinstance(item, dict):
                continue
            nested = item.get("data")
            if isinstance(nested, dict) and _looks_like_profile(nested):
                return nested
            parsed = _parse_json_object(str(item.get("text") or ""))
            if parsed and (_looks_like_profile(parsed) or parsed.get("error")):
                return parsed
    if _looks_like_profile(result):
        return result
    return None


def fetch_linkedin_mcp_payload(ref: LinkedInProfileRef) -> Optional[dict]:
    """JSON-RPC tools/call against a configured LinkedIn MCP. None if unset/fails."""
    dump = fetch_linkedin_mcp_debug(ref)
    payload = dump.get("payload")
    return payload if isinstance(payload, dict) else None


def _redact_secrets(text: str) -> str:
    import re

    out = re.sub(r"li_at=[^;\s]+", "li_at=REDACTED", text or "", flags=re.I)
    cookie = (os.environ.get("LINKEDIN_COOKIE") or "").strip()
    if cookie and len(cookie) > 8:
        out = out.replace(cookie, "REDACTED")
    return out


def _argument_sets(ref: LinkedInProfileRef) -> list[dict[str, object]]:
    handle = ref.handle
    url = ref.url
    sections = [
        "experience",
        "education",
        "skills",
        "languages",
        "projects",
        "certifications",
    ]
    return [
        {"profile": url},
        {"profile": handle, "sections": sections},
        {"url": url},
        {"username": handle},
        {"publicIdentifier": handle},
    ]


def fetch_linkedin_mcp_debug(ref: LinkedInProfileRef) -> dict[str, object]:
    """Call get_profile and keep raw replies for local debugging.

    # Ref: uvx linkedin-api-mcp stdio — stderr must be drained or Windows pipes hang
    """
    command = _mcp_command()
    empty: dict[str, object] = {
        "command": command,
        "tools": [],
        "payload": None,
        "replies": [],
        "stderr_tail": "",
        "error": "no_uvx" if not command else "",
    }
    if not command:
        return empty
    tool_name = (os.environ.get("LINKEDIN_MCP_TOOL") or "").strip()
    timeout = int(os.environ.get("LINKEDIN_MCP_TIMEOUT_SEC") or "180")
    box: dict[str, object] = {
        "command": command,
        "tools": [],
        "payload": None,
        "replies": [],
        "stderr_tail": "",
        "error": "",
    }

    def _run() -> None:
        from threading import Thread

        stderr_chunks: list[str] = []
        try:
            proc = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(PROJECT_ROOT),
                env=_child_env(),
            )
        except OSError as exc:
            box["error"] = str(exc)
            return
        drain = Thread(target=lambda: _drain_stderr(proc, stderr_chunks), daemon=True)
        drain.start()
        try:
            _write_rpc(
                proc,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "jobhunter", "version": "0.1.0"},
                    },
                },
            )
            init_reply = _read_rpc(proc)
            box["replies"] = list(box.get("replies") or []) + [{"stage": "initialize", "body": init_reply}]
            _write_rpc(
                proc,
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            _write_rpc(
                proc,
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
            listed = _read_rpc(proc)
            tools = []
            result = listed.get("result") if isinstance(listed, dict) else None
            if isinstance(result, dict):
                tools = [
                    str(item.get("name") or "")
                    for item in (result.get("tools") or [])
                    if isinstance(item, dict)
                ]
            box["tools"] = [name for name in tools if name]
            box["replies"] = list(box.get("replies") or []) + [{"stage": "tools/list", "body": listed}]
            names = [tool_name] if tool_name else ["get_profile"]
            listed_names = list(box["tools"] or [])
            if listed_names:
                names = [name for name in names if name in listed_names] or [
                    item for item in listed_names if "profile" in item and "company" not in item
                ][:1]
            next_id = 3
            for name in names[:1]:
                for arguments in _argument_sets(ref)[:2]:
                    _write_rpc(
                        proc,
                        {
                            "jsonrpc": "2.0",
                            "id": next_id,
                            "method": "tools/call",
                            "params": {"name": name, "arguments": arguments},
                        },
                    )
                    next_id += 1
                    reply = _read_rpc(proc)
                    mapped = _unwrap_tool_result(reply)
                    box["replies"] = list(box.get("replies") or []) + [
                        {"stage": f"tools/call:{name}", "arguments": arguments, "body": reply}
                    ]
                    if isinstance(mapped, dict) and mapped.get("error"):
                        box["error"] = str(mapped.get("error"))
                        continue
                    if isinstance(mapped, dict) and _looks_like_profile(mapped):
                        box["payload"] = mapped
                        box["error"] = ""
                        return
        except Exception as exc:
            box["error"] = str(exc)[:400]
            return
        finally:
            drain.join(timeout=1)
            box["stderr_tail"] = _redact_secrets("".join(stderr_chunks))[-4000:]
            try:
                proc.kill()
            except Exception:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
                pass

    from threading import Thread

    worker = Thread(target=_run, daemon=True)
    worker.start()
    worker.join(timeout)
    if worker.is_alive() and not box.get("payload"):
        box["error"] = box.get("error") or f"timeout after {timeout}s"
    return box


def _drain_stderr(proc: subprocess.Popen[bytes], sink: list[str]) -> None:
    try:
        assert proc.stderr is not None
        while True:
            chunk = proc.stderr.read(4096)
            if not chunk:
                break
            sink.append(chunk.decode("utf-8", errors="replace"))
    except Exception:
        return


def dump_linkedin_mcp(raw_username: str, out_path: Optional[Path] = None) -> dict[str, object]:
    """Fetch one profile and write the raw MCP JSON (cookie redacted)."""
    from contact_links import parse_linkedin_profile_ref

    ref = parse_linkedin_profile_ref(raw_username)
    if ref is None:
        raise ValueError("not a LinkedIn /in/ URL or username")
    debug = fetch_linkedin_mcp_debug(ref)
    folder = PROJECT_ROOT / "config" / "linkedin_mcp"
    folder.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (ref.handle or "profile"))
    path = out_path or (folder / f"{safe}_raw.json")
    payload = {
        "handle": ref.handle,
        "url": ref.url,
        "command": debug.get("command"),
        "tools": debug.get("tools"),
        "error": debug.get("error"),
        "stderr_tail": debug.get("stderr_tail"),
        "payload": debug.get("payload"),
        "replies": debug.get("replies"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    debug["out_path"] = str(path)
    return debug


def _unfence(text: str) -> str:
    """Strip LinkedIn MCP prompt-injection fences; keep the scraped body."""
    raw = (text or "").strip()
    if "LINKEDIN-UNTRUSTED-DATA" not in raw:
        return raw
    parts = raw.split("\n---\n")
    if len(parts) >= 3:
        return parts[1].strip()
    return raw


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _unfence(value.strip())
    if isinstance(value, dict):
        for key in (
            "name",
            "text",
            "title",
            "label",
            "companyName",
            "schoolName",
            "language",
        ):
            inner = value.get(key)
            if isinstance(inner, str) and inner.strip():
                return _unfence(inner.strip())
    return _unfence(str(value).strip())


def _experience_rows(raw: object) -> list[dict]:
    rows: list[dict] = []
    for item in _as_list(raw):
        if not isinstance(item, dict):
            continue
        company = _as_text(
            item.get("companyName")
            or item.get("company")
            or item.get("organization")
        )
        role = _as_text(item.get("title") or item.get("role") or item.get("position"))
        if not company and not role:
            continue
        if not company:
            company = role
        period = _as_text(
            item.get("dates")
            or item.get("period")
            or " - ".join(
                part
                for part in (
                    _as_text(item.get("startDate") or item.get("start") or item.get("dateFrom")),
                    _as_text(item.get("endDate") or item.get("end") or item.get("dateTo")),
                )
                if part
            )
        )
        summary = _as_text(item.get("description") or item.get("summary"))
        highlights = [summary] if summary else []
        rows.append(
            {
                "company": company,
                "role": role,
                "period": period,
                "highlights": highlights,
                "skills_used": [],
                "roles": [
                    {
                        "role": role,
                        "period": period,
                        "highlights": highlights,
                        "skills_used": [],
                    }
                ],
            }
        )
    return rows


def _education_rows(raw: object) -> list[dict]:
    rows: list[dict] = []
    for item in _as_list(raw):
        if not isinstance(item, dict):
            continue
        school = _as_text(item.get("schoolName") or item.get("school") or item.get("institution"))
        if not school:
            continue
        rows.append(
            {
                "institution": school,
                "degree": _as_text(item.get("degreeName") or item.get("degree")),
                "field": _as_text(item.get("fieldOfStudy") or item.get("field") or item.get("field_of_study")),
                "year": _as_text(item.get("dates") or item.get("year") or item.get("endDate") or item.get("end")),
            }
        )
    return rows


def _skill_tags(raw: object) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for item in _as_list(raw):
        label = _as_text(
            (item.get("name") or item.get("language")) if isinstance(item, dict) else item
        )
        key = label.lower()
        if label and key not in seen:
            tags.append(label)
            seen.add(key)
    return tags[:40]


def _language_items(raw: object) -> list[dict[str, Optional[str]]]:
    rows: list[dict[str, Optional[str]]] = []
    seen: set[str] = set()
    for item in _as_list(raw):
        if isinstance(item, dict):
            name = _as_text(item.get("name") or item.get("language") or item)
            level = _as_text(
                item.get("proficiency")
                or item.get("level")
                or item.get("proficiencyLevel")
            )
        else:
            name = _as_text(item)
            level = ""
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        rows.append({"name": name, "proficiency": level or None})
    return rows


def master_profile_from_mcp(payload: dict, ref: LinkedInProfileRef) -> dict:
    """Map LinkedIn MCP get_profile JSON onto master_profile.example.json.

    # Ref: config/master_profile.example.json
    """
    data = payload
    for key in ("profile", "data", "person", "result"):
        inner = data.get(key) if isinstance(data, dict) else None
        if isinstance(inner, dict) and (
            inner.get("firstName")
            or inner.get("headline")
            or inner.get("lastName")
            or inner.get("name")
            or inner.get("public_id")
        ):
            data = inner
            break
    if not isinstance(data, dict):
        data = {}
    first = _as_text(data.get("firstName") or data.get("first_name"))
    last = _as_text(data.get("lastName") or data.get("last_name"))
    name = _as_text(data.get("fullName") or data.get("name") or f"{first} {last}")
    if is_placeholder_profile_name(name):
        name = name_from_linkedin_handle(ref.handle)
    location = _as_text(
        data.get("location")
        or data.get("geoLocationName")
        or data.get("geo")
        or "Hong Kong"
    )
    if isinstance(data.get("geo"), dict):
        location = _as_text(data["geo"].get("full") or data["geo"].get("country")) or location
    headline = _as_text(data.get("headline"))
    about = _as_text(data.get("about") or data.get("summary") or data.get("description"))
    experience = _experience_rows(data.get("experience") or data.get("positions"))
    if not experience:
        current = data.get("current_position")
        if isinstance(current, dict):
            experience = _experience_rows([current])
    education = _education_rows(data.get("education") or data.get("schools"))
    skills = _skill_tags(data.get("skills") or data.get("skill"))
    language_items = _language_items(data.get("languages"))
    language_labels = [
        f"{item['name']} ({item['proficiency']})" if item.get("proficiency") else str(item["name"])
        for item in language_items
    ]
    projects = []
    for item in data.get("projects") or []:
        if not isinstance(item, dict):
            continue
        pname = _as_text(item.get("name"))
        if not pname:
            continue
        projects.append(
            {
                "name": pname,
                "period": _as_text(item.get("dates") or item.get("period")),
                "description": _as_text(item.get("description")),
                "tech_stack": [],
                "is_side_project": False,
            }
        )
    certifications = []
    for item in data.get("certifications") or []:
        if not isinstance(item, dict):
            continue
        cname = _as_text(item.get("name"))
        if not cname:
            continue
        year_raw = _as_text(item.get("issued") or item.get("year"))
        year_num: int | None = None
        digits = "".join(ch for ch in year_raw if ch.isdigit())
        if len(digits) >= 4:
            year_num = int(digits[:4])
        certifications.append(
            {
                "name": cname,
                "issuer": _as_text(item.get("issuer")),
                "year": year_num,
            }
        )
    target_roles = [headline] if headline else []
    handle = _as_text(data.get("public_id")) or ref.handle
    return {
        "basics": {
            "name": name or name_from_linkedin_handle(handle),
            "location": location or "Hong Kong",
            "email": _as_text(data.get("email")),
            "phone": _as_text(data.get("phone") or data.get("mobile")),
            "address": "",
            "website": _as_text(data.get("website") or data.get("websites")),
            "github": "",
            "linkedin": handle,
            "headline": headline,
            "summary": about,
            "target_roles": target_roles,
            "languages": language_labels,
        },
        "education": education,
        "technical_skills": {"linkedin": skills} if skills else {},
        "experience": experience,
        "projects": projects,
        "certifications": certifications,
        "languages": language_items,
        "awards": [],
    }


def write_linkedin_mcp_cache(candidate_id: str, payload: dict, mapped: dict) -> Path:
    """Write the last MCP get_profile result next to the candidate JSON.

    # Ref: config/linkedin_mcp/{id}.json — not Cursor, not SQLite
    """
    folder = PROJECT_ROOT / "config" / "linkedin_mcp"
    folder.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (candidate_id or "default"))
    path = folder / f"{safe}.json"
    slim = {
        "candidate_id": candidate_id,
        "public_id": payload.get("public_id") if isinstance(payload, dict) else None,
        "profile_url": payload.get("profile_url") if isinstance(payload, dict) else None,
        "mapped_basics": mapped.get("basics") if isinstance(mapped, dict) else {},
        "experience_count": len(mapped.get("experience") or []) if isinstance(mapped, dict) else 0,
        "education_count": len(mapped.get("education") or []) if isinstance(mapped, dict) else 0,
        "payload": payload,
    }
    path.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def linkedin_mcp_status() -> dict[str, str | int | bool]:
    """Where Jobhunter attaches LinkedIn MCP and how a fetch is used.

    # Ref: FastAPI/Milo stdio — not Cursor MCP
    """
    _load_agent_env()
    command = _mcp_command()
    cookie = bool((os.environ.get("LINKEDIN_COOKIE") or "").strip())
    tool = (os.environ.get("LINKEDIN_MCP_TOOL") or "get_profile").strip() or "get_profile"
    timeout = int(os.environ.get("LINKEDIN_MCP_TIMEOUT_SEC") or "120")
    return {
        "connected_in": "Jobhunter FastAPI / Milo stdio child — not Cursor",
        "command": " ".join(command) if command else "uvx linkedin-api-mcp (uvx not on PATH)",
        "tool": tool,
        "timeout_sec": timeout,
        "session": (
            "OS keyring after `uvx linkedin-api-mcp auth`, "
            "or LINKEDIN_COOKIE in Jobhunter .env (never stored in Telegram)"
        ),
        "cookie_env_set": cookie,
        "how": (
            "Profile Import LinkedIn → POST /api/candidates/import-linkedin "
            "spawns MCP get_profile(profile, sections), maps experience/"
            "education/skills into the person JSON, cache at "
            "config/linkedin_mcp/{id}.json"
        ),
        "writes_profile": "config/master_profile.json or config/profiles/{tag}.json",
        "writes_cache": "config/linkedin_mcp/{id}.json",
        "uvx_found": bool(_find_uvx()),
        "ready": bool(command),
    }


def mcp_status_lines() -> list[str]:
    """Plain lines for Telegram / dashboard copy."""
    status = linkedin_mcp_status()
    cookie = "yes" if status["cookie_env_set"] else "no"
    return [
        f"Where: {status['connected_in']}",
        f"Command: {status['command']}",
        f"Tool: {status['tool']}(profile, sections)",
        f"Timeout: {status['timeout_sec']}s",
        f"Session: {status['session']}",
        f"LINKEDIN_COOKIE in env: {cookie}",
        f"How: {status['how']}",
        f"Profile file: {status['writes_profile']}",
        f"MCP cache: {status['writes_cache']}",
    ]
