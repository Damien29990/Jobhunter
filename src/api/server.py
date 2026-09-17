"""Jobhunter Dashboard API — FastAPI read-only layer over job_agent.db.

Spawns agent subprocesses on demand (agents own DB writes; the dashboard
never writes). Serves generated artifacts (CV PDFs, dossier Markdown,
checklists) from the real paths stored in the DB.

# Ref: workspace rule — src/api/ for API; Pydantic v2 strict; Asia/Hong_Kong
# time; deterministic gates imported from agents (gates.py), no LLM guessing.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.datastructures import UploadFile as StarletteUploadFile

# Load .env once at server startup so TELEGRAM_BOT_TOKEN, SCHEDULER_HOURS, etc.
# are available to all modules (telegram_notifier, scheduler) without restart.
# # Ref: server must call load_dotenv() — agents do it in their __main__,
# # but the server process itself needs it too.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_AGENTS_DIR = (Path(__file__).resolve().parent.parent / "agents")
if str(_AGENTS_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENTS_DIR))

from . import gates  # noqa: E402
from .agent_runner import LOG_FILE, runner  # noqa: E402
from .mdrender import markdown_to_html  # noqa: E402
from activity_logger import log_system  # noqa: E402
from .models import (  # noqa: E402
    AgentRunRequest, AgentStatus, AgentStatusMap, CandidateProfile,
    CompanyDossierOut, CreateProfileRequest, DossierPayload, FunnelStats,
    HealthOut, JobCheckResult, JobListResponse, JobOut, JobShelfResponse,
    JobStatusUpdate, Profile, TelegramBotOut,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "job_agent.db"
PROFILES_DIR = PROJECT_ROOT / "config" / "profiles"
DEFAULT_PROFILE = PROJECT_ROOT / "config" / "master_profile.json"


def _connect() -> sqlite3.Connection:
    if not DB_PATH.is_file():
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        return conn
    uri = f"file:{DB_PATH.as_posix()}?mode=ro&uri=true"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=5000;")
    except Exception:
        pass
    return conn


def _row_to_job(row: sqlite3.Row) -> JobOut:
    data = dict(row)
    try:
        from listing_filters import display_listing_title, normalize_listing_url

        if data.get("job_url"):
            data["job_url"] = normalize_listing_url(str(data["job_url"]))
        if data.get("job_title"):
            data["job_title"] = display_listing_title(
                str(data["job_title"]), str(data.get("job_url") or "")
            ) or data["job_title"]
    except Exception:
        pass
    return JobOut.model_validate(data)


def _under_project(path: Path) -> bool:
    """True when path resolves inside the Jobhunter repo (Windows-safe)."""
    try:
        resolved = path.resolve()
        root = PROJECT_ROOT.resolve()
        return os.path.commonpath([str(resolved), str(root)]) == str(root)
    except Exception:
        return False


def _dossier_row_for_company(conn: sqlite3.Connection, company_name: Optional[str]) -> Optional[sqlite3.Row]:
    """Match a job's employer to company_dossiers (case-insensitive trim)."""
    if not company_name or not str(company_name).strip():
        return None
    return conn.execute(
        "SELECT * FROM company_dossiers "
        "WHERE lower(trim(company_name)) = lower(trim(?))",
        (company_name,),
    ).fetchone()


def _dossier_lookup(conn: sqlite3.Connection) -> dict[str, CompanyDossierOut]:
    """Map lower(company_name) → typed dossier for attaching onto jobs."""
    rows = conn.execute("SELECT * FROM company_dossiers").fetchall()
    out: dict[str, CompanyDossierOut] = {}
    for row in rows:
        item = _row_to_dossier(row)
        out[item.company_name.strip().lower()] = item
    return out


def _attach_dossier(job: JobOut, lookup: dict[str, CompanyDossierOut]) -> JobOut:
    if not job.company_name:
        return job
    found = lookup.get(job.company_name.strip().lower())
    if found is None:
        return job
    return job.model_copy(update={"dossier": found})


def _jobs_for_company(conn: sqlite3.Connection, company_name: str) -> list[JobOut]:
    """Jobs whose employer name matches a dossier, case-insensitive.

    # Ref: dashboard-frontend-expert company dossier — linked jobs below the brief.
    """
    rows = conn.execute(
        "SELECT * FROM job_postings "
        "WHERE lower(trim(company_name)) = lower(trim(?)) "
        "ORDER BY COALESCE(expired, 0) ASC, match_score DESC",
        (company_name,),
    ).fetchall()
    return [_row_to_job(r) for r in rows]


def _row_to_dossier(
    row: sqlite3.Row,
    *,
    jobs: Optional[list[JobOut]] = None,
    job_count: Optional[int] = None,
) -> CompanyDossierOut:
    data = dict(row)
    raw = data.get("dossier_json")
    dossier = DossierPayload()
    if raw:
        try:
            parsed = json.loads(raw, strict=False) if isinstance(raw, str) else raw
            if isinstance(parsed, dict):
                dossier = DossierPayload.model_validate(parsed)
        except Exception:
            dossier = DossierPayload()
    data["dossier"] = dossier
    if jobs is not None:
        data["linked_jobs"] = jobs
        data["job_count"] = len(jobs)
    elif job_count is not None:
        data["job_count"] = job_count
    return CompanyDossierOut.model_validate(data)


def _typed_dossier_markdown(out: CompanyDossierOut) -> str:
    """Rebuild a readable brief from the typed payload when the .md file is missing."""
    d = out.dossier
    verdict = out.vetting_verdict or d.vetting_verdict or "—"
    confidence = out.confidence if out.confidence is not None else d.confidence
    news = d.recent_news_and_events or []
    red = d.red_flags or []
    green = d.green_flags or []
    qs = d.reverse_interview_questions or []
    tech = d.detected_tech_stack or []
    urls = out.source_urls or d.source_urls or []

    def bullets(items: list[str]) -> str:
        cleaned = [str(i).strip() for i in items if str(i).strip()]
        if not cleaned:
            return "_None recorded from available sources._"
        return "\n".join(f"- {item}" for item in cleaned)

    return f"""# {out.company_name} — Due Diligence Dossier

- **Verdict:** {verdict}
- **Confidence:** {confidence if confidence is not None else "—"}/100
- **Salary benchmark:** {d.salary_benchmark or "Not disclosed"}

## Engineering culture
{d.engineering_culture or "_Insufficient public detail._"}

## Detected tech stack
{bullets(tech)}

## Architectural trade-offs / technical debt
{d.architectural_trade_offs or "_See JD and official scope._"}

## Glassdoor / employee sentiment
{d.glassdoor_sentiment or "_No direct review scores in sources._"}

## Recent news and events
{bullets(news)}

## Green flags
{bullets(green)}

## Red flags
{bullets(red)}

## Reverse-interview questions
{bullets(qs)}

## Sources
{bullets(urls)}
"""


app = FastAPI(title="Jobhunter Dashboard API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5174", "http://127.0.0.1:5174",
    ],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


def _ensure_expired_column() -> None:
    """One-time schema migration for dashboard-managed job flags.

    Adds `expired` and `user_status` (UNCONSIDERABLE). Agents still read every
    row; the dashboard only hides them from the main kanban.
    """
    if not DB_PATH.is_file():
        return
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(job_postings)").fetchall()}
        if "expired" not in cols:
            conn.execute("ALTER TABLE job_postings ADD COLUMN expired BOOLEAN DEFAULT 0")
        if "user_status" not in cols:
            conn.execute("ALTER TABLE job_postings ADD COLUMN user_status TEXT")
        conn.commit()
    except Exception:
        pass
    try:
        _rewrite_phenom_job_urls(conn)
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def _rewrite_phenom_job_urls(conn: sqlite3.Connection) -> None:
    """Persist openable HKJC Phenom URLs (locale prefix)."""
    try:
        from listing_filters import display_listing_title, normalize_listing_url
    except Exception:
        return
    try:
        rows = conn.execute("SELECT id, job_url, job_title FROM job_postings").fetchall()
    except Exception:
        return
    for row in rows:
        job_id, url, title = row[0], row[1], row[2]
        new_url = normalize_listing_url(url or "")
        new_title = display_listing_title(title or "", new_url or url or "")
        if new_url == (url or "") and new_title == (title or ""):
            continue
        try:
            conn.execute(
                "UPDATE job_postings SET job_url = ?, job_title = ? WHERE id = ?",
                (new_url or url, new_title or title, job_id),
            )
        except sqlite3.IntegrityError:
            continue


def _active_job_clause() -> tuple[str, list]:
    """SQL fragment: visible on the main kanban (score ≥ 35, not expired, not unconsiderable)."""
    return (
        "COALESCE(match_score, 0) >= ? AND COALESCE(expired, 0) = 0 "
        "AND UPPER(COALESCE(user_status, '')) != ?",
        [gates.DASHBOARD_MIN_DISPLAY_SCORE, gates.USER_STATUS_UNCONSIDERABLE],
    )


@app.on_event("startup")
def _on_startup() -> None:
    _ensure_expired_column()


def _connect_rw() -> sqlite3.Connection:
    """Read-write connection for the dashboard's explicit write endpoints
    (expire/reactivate). WAL + busy_timeout keep it from blocking agents."""
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def _fetch_job_page(url: str, timeout: float = 12.0):
    """GET the source page. Returns (ok, status_code, final_url, reason, text).

    # Ref: HEAD alone misses 405 and cannot verify the JD title
    """
    headers = {"User-Agent": "Mozilla/5.0 (Jobhunter dashboard link-checker)"}
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
            r = client.get(url)
            ok = r.status_code < 400 and r.status_code not in (404, 410)
            text = (r.text or "")[:80000] if ok else ""
            reason = "ok" if ok else f"HTTP {r.status_code}"
            return ok, r.status_code, str(r.url), reason, text
    except httpx.HTTPError as exc:
        return False, None, url, f"HTTP error: {exc}", ""
    except Exception as exc:
        return False, None, url, f"error: {exc}", ""


@app.get("/api/health", response_model=HealthOut)
def health() -> HealthOut:
    conn = _connect()
    try:
        try:
            jobs = conn.execute("SELECT COUNT(*) FROM job_postings").fetchone()[0]
        except Exception:
            jobs = 0
        try:
            dossiers = conn.execute("SELECT COUNT(*) FROM company_dossiers").fetchone()[0]
        except Exception:
            dossiers = 0
    finally:
        conn.close()
    return HealthOut(status="ok", db_path=str(DB_PATH), job_count=jobs, dossier_count=dossiers)


@app.get("/api/telegram/bot", response_model=TelegramBotOut)
def telegram_bot() -> TelegramBotOut:
    """Public Telegram bot handle so the dashboard can link to t.me/<username>.

    Token is never returned. Username comes from TELEGRAM_BOT_USERNAME or getMe.
    # Ref: Telegram Bot API getMe
    """
    from .telegram_notifier import get_bot_info
    info = get_bot_info()
    return TelegramBotOut.model_validate(info)


def _profile_name(p: Path) -> str:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        name = (data.get("basics") or {}).get("name")
        if name:
            return str(name)
    except Exception:
        pass
    return p.stem


def _profile_roles(p: Path) -> list[str]:
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        roles = (data.get("basics") or {}).get("target_roles") or []
        return [str(r) for r in roles]
    except Exception:
        return []


@app.get("/api/candidates", response_model=list[CandidateProfile])
def candidates() -> list[CandidateProfile]:
    out: list[CandidateProfile] = []
    if PROFILES_DIR.is_dir():
        for p in sorted(PROFILES_DIR.glob("*.json")):
            out.append(CandidateProfile(
                id=p.stem, name=_profile_name(p), profile_path=str(p),
                target_roles=_profile_roles(p), is_default=False,
            ))
    if DEFAULT_PROFILE.is_file():
        out.append(CandidateProfile(
            id="default", name=_profile_name(DEFAULT_PROFILE),
            profile_path=str(DEFAULT_PROFILE), target_roles=_profile_roles(DEFAULT_PROFILE),
            is_default=True,
        ))
    seen: set[str] = set()
    deduped: list[CandidateProfile] = []
    for c in out:
        if c.id in seen:
            continue
        seen.add(c.id)
        deduped.append(c)
    return deduped


# ---------------------------------------------------------------------------
# Profile editor — read / write / create (writes ONLY to config/ profile JSON
# files; never touches src/agents, templates, or job_agent.db).
# ---------------------------------------------------------------------------

_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def _profile_path_for(id: str) -> Path:
    """Resolve a candidate id to its JSON file, safely.

    'default' -> config/master_profile.json
    else      -> config/profiles/{id}.json
    Rejects path traversal and invalid ids.
    """
    if not id or not _PROFILE_ID_RE.match(id):
        raise HTTPException(400, f"invalid profile id: {id!r}")
    if id == "default":
        path = DEFAULT_PROFILE
    else:
        path = PROFILES_DIR / f"{id}.json"
    try:
        resolved = path.resolve()
        resolved.relative_to(PROJECT_ROOT / "config")
    except Exception:
        raise HTTPException(400, "invalid profile path")
    return resolved


@app.get("/api/candidates/{id}", response_model=Profile)
def get_candidate(id: str) -> Profile:
    path = _profile_path_for(id)
    if not path.is_file():
        raise HTTPException(404, f"profile {id!r} not found")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(422, f"profile is not valid JSON: {exc}")
    try:
        return Profile.model_validate(data)
    except Exception as exc:
        raise HTTPException(422, f"profile failed validation: {exc}")


@app.put("/api/candidates/{id}", response_model=Profile)
def put_candidate(id: str, profile: Profile) -> Profile:
    path = _profile_path_for(id)
    # Re-validate (model_validate) and write back, preserving extra keys.
    data = profile.model_dump(mode="json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


@app.post("/api/candidates", response_model=Profile, status_code=201)
def create_candidate(req: CreateProfileRequest) -> Profile:
    if not req.id or not _PROFILE_ID_RE.match(req.id):
        raise HTTPException(400, f"invalid profile id: {req.id!r}")
    path = _profile_path_for(req.id)
    if path.is_file():
        raise HTTPException(409, f"profile {req.id!r} already exists")
    profile = Profile(
        basics={"name": req.name, "location": req.location or "Hong Kong",
                "target_roles": [], "min_expected_salary_hkd": None, "languages": []},
        education=[], technical_skills={}, experience=[], projects=[], certifications=[],
    )
    data = profile.model_dump(mode="json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def _merge_parsed_profile(profile_path: Path, parsed: dict) -> dict:
    """Merge Ollama CV parse output into the candidate JSON on disk."""
    if profile_path.is_file():
        existing = json.loads(profile_path.read_text(encoding="utf-8"))
    else:
        existing = {}
    for key in ("basics", "education", "technical_skills", "experience", "projects", "certifications"):
        if parsed.get(key):
            if key == "basics":
                existing.setdefault("basics", {}).update(parsed["basics"])
            elif key == "technical_skills":
                existing.setdefault("technical_skills", {}).update(parsed["technical_skills"])
            elif key == "experience":
                from milo_intake import normalize_experience_list as _norm_exp
                existing[key] = _norm_exp(parsed[key]) if isinstance(parsed[key], list) else parsed[key]
            else:
                existing[key] = parsed[key]
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return existing


# ---------------------------------------------------------------------------
# Milo endpoints — CV import, chatbot, summary, history
# # Ref: Agent 0 — Exploratory Summarizer / Context Expander
# ---------------------------------------------------------------------------

_CV_ATTACH_SUFFIXES = {".pdf", ".txt", ".md", ".docx", ".text"}
_MAX_ATTACH_BYTES = 5 * 1024 * 1024
_MAX_ATTACH_FILES = 3


@app.post("/api/candidates/import-cv")
async def import_cv_endpoint(request: Request, candidate_id: Optional[str] = Query(None)):
    """Import a CV (JSON, form text, or uploaded file) and parse it via Ollama."""
    cv_text = ""
    cid = candidate_id
    stored: dict = {}
    ctype = (request.headers.get("content-type") or "").lower()
    if "application/json" in ctype:
        body = await request.json()
        if isinstance(body, dict):
            cid = cid or body.get("candidate_id")
            cv_text = str(body.get("cv_text") or "")
    elif "multipart/form-data" in ctype:
        form = await request.form()
        cid = cid or str(form.get("candidate_id") or "") or None
        cv_text = str(form.get("cv_text") or "")
        upload = form.get("file")
        if isinstance(upload, StarletteUploadFile):
            data = await upload.read()
            filename = upload.filename or "cv.bin"
            if len(data) > _MAX_ATTACH_BYTES:
                raise HTTPException(400, f"{filename}: file exceeds 5MB")
            from milo_intake import extract_text_from_bytes, store_cv_upload
            stored = store_cv_upload(cid or "default", filename, data)
            try:
                cv_text = extract_text_from_bytes(filename, data)
            except RuntimeError as exc:
                raise HTTPException(400, str(exc)) from exc
    if not cv_text.strip():
        raise HTTPException(400, "cv_text or file is required")
    profile_path = _profile_path_for(cid or "default")
    from milo_intake import import_cv as _import_cv
    parsed = _import_cv(cv_text)
    if not parsed:
        raise HTTPException(503, "Ollama unavailable or CV parsing failed")
    existing = _merge_parsed_profile(profile_path, parsed)
    if stored:
        uploads = list(existing.get("cv_uploads") or [])
        uploads.append(stored)
        existing["cv_uploads"] = uploads[-20:]
        profile_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    from milo_intake import MiloIntakeAgent
    agent = MiloIntakeAgent(profile_path=profile_path)
    readme_path = agent.refresh_readme(source="cv_import")
    existing["milo_readme_path"] = str(readme_path)
    return existing


@app.post("/api/milo/chat")
async def milo_chat(request: Request):
    """Chat with Milo. JSON {candidate_id, message} or multipart with files."""
    ctype = (request.headers.get("content-type") or "").lower()
    attachment_names: list[str] = []
    imported_files: list[str] = []
    prompt_extra = ""
    candidate_id = "default"
    message = ""

    if "multipart/form-data" in ctype:
        form = await request.form()
        candidate_id = str(form.get("candidate_id") or "default")
        message = str(form.get("message") or "")
        uploads = [
            u for u in form.getlist("files")
            if isinstance(u, StarletteUploadFile)
        ][:_MAX_ATTACH_FILES]
        chunks: list[str] = []
        from milo_intake import extract_text_from_bytes, import_cv as _import_cv
        profile_path = _profile_path_for(candidate_id)
        for up in uploads:
            data = await up.read()
            filename = up.filename or "attachment"
            if len(data) > _MAX_ATTACH_BYTES:
                raise HTTPException(400, f"{filename}: file exceeds 5MB")
            try:
                text = extract_text_from_bytes(filename, data)
            except RuntimeError as exc:
                raise HTTPException(400, str(exc)) from exc
            text = (text or "").strip()
            if not text:
                raise HTTPException(400, f"{filename}: no text could be extracted")
            chunks.append(f"[Attached: {filename}]\n{text[:8000]}")
            attachment_names.append(filename)
            suffix = Path(filename).suffix.lower()
            if suffix in _CV_ATTACH_SUFFIXES and len(text) >= 80:
                from milo_intake import store_cv_upload
                stored = store_cv_upload(candidate_id, filename, data)
                parsed = _import_cv(text)
                if parsed:
                    merged = _merge_parsed_profile(profile_path, parsed)
                    uploads = list(merged.get("cv_uploads") or [])
                    uploads.append(stored)
                    merged["cv_uploads"] = uploads[-20:]
                    profile_path.write_text(
                        json.dumps(merged, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    imported_files.append(filename)
        prompt_extra = "\n\n".join(chunks)
    else:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(400, "message is required")
        if not isinstance(body, dict):
            raise HTTPException(400, "message is required")
        candidate_id = str(body.get("candidate_id") or "default")
        message = str(body.get("message") or "")

    display = message.strip()
    if attachment_names:
        display = (display + "\n" if display else "") + f"[Attached: {', '.join(attachment_names)}]"
        if imported_files:
            display += "\n[CV imported into profile]"
    if not display:
        raise HTTPException(400, "message or file is required")

    from milo_intake import MiloIntakeAgent
    profile_path = _profile_path_for(candidate_id)
    agent = MiloIntakeAgent(profile_path=profile_path)
    if imported_files:
        agent.refresh_readme(source="cv_import")
    result = agent.chat(display, prompt_extra=prompt_extra)
    result["attachments"] = attachment_names
    result["imported_files"] = imported_files
    return result


@app.get("/api/milo/summary/{candidate_id}")
def milo_summary_endpoint(candidate_id: str):
    """Get Milo's shared README and chat count for a candidate."""
    from milo_intake import MiloIntakeAgent
    from milo_context import load_milo_readme, milo_readme_path_for, live_chat_messages
    profile_path = _profile_path_for(candidate_id)
    agent = MiloIntakeAgent(profile_path=profile_path)
    live = live_chat_messages(agent.chat_history)
    readme_path = milo_readme_path_for(profile_path)
    return {
        "executive_narrative": agent.milo_summary or (agent.profile.get("acceptance_context") or {}).get("executive_narrative", ""),
        "chat_count": len(live),
        "readme_path": str(readme_path),
        "readme": load_milo_readme(profile_path),
    }


@app.get("/api/milo/history/{candidate_id}")
def milo_history_endpoint(candidate_id: str):
    """Get full chat history for a candidate."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT role, content, created_at FROM milo_chat_history WHERE candidate_id = ? ORDER BY id",
            (candidate_id,),
        ).fetchall()
        return {"messages": [dict(r) for r in rows], "count": len(rows)}
    finally:
        conn.close()


@app.get("/api/jobs", response_model=JobListResponse)
def list_jobs(
    candidate_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None),
    source_lane: Optional[str] = Query(None),
    target_industry: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    view: Literal["active", "all"] = Query("active"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> JobListResponse:
    conn = _connect()
    try:
        where: list[str] = []
        params: list = []
        if min_score is not None:
            where.append("(match_score >= ? OR transferability_score >= ?)")
            params += [min_score, gates.DISCOVERED_TRANSFER_FLOOR]
        if status:
            where.append("cv_status = ?"); params.append(status)
        if source_lane:
            where.append("source_lane = ?"); params.append(source_lane)
        if target_industry:
            where.append("target_industry = ?"); params.append(target_industry)
        if q:
            where.append("(company_name LIKE ? OR job_title LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
        if view == "active":
            clause, extra = _active_job_clause()
            where.append(f"({clause})")
            params += extra
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        total = conn.execute(
            f"SELECT COUNT(*) FROM job_postings {where_sql}", params
        ).fetchone()[0]
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"SELECT * FROM job_postings {where_sql} "
            f"ORDER BY COALESCE(expired,0) ASC, COALESCE(match_score,0) DESC, created_at DESC "
            f"LIMIT ? OFFSET ?",
            params + [page_size, offset],
        ).fetchall()
        lookup = _dossier_lookup(conn)
        items = [_attach_dossier(_row_to_job(r), lookup) for r in rows]
        return JobListResponse(items=items, total=total, page=page, page_size=page_size)
    finally:
        conn.close()


@app.get("/api/jobs/summary")
def jobs_summary(
    stage: Optional[Literal["all", "dana", "leo", "clara"]] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
):
    """Lightweight list for the job-id dropdown, filtered by pipeline stage.

    Declared BEFORE /api/jobs/{job_id} so the dynamic {job_id} route
    doesn't shadow it. Stage filters mirror each agent's "next step":
      dana  -> jobs pending vetting (score gate, no dossier yet)
      leo   -> vetted-PROCEED jobs with no CV yet
      clara -> jobs with a CV (MATERIALS_GENERATED), not yet application_ready
      all/None -> every job
    """
    conn = _connect()
    try:
        if stage == "dana":
            rows = conn.execute(
                "SELECT j.id AS id, j.job_title AS job_title, "
                "j.company_name AS company_name, j.match_score AS match_score "
                "FROM job_postings j "
                "LEFT JOIN company_dossiers d ON d.company_name = j.company_name "
                "WHERE d.id IS NULL "
                "AND (j.match_score >= ? OR j.transferability_score >= ?) "
                "ORDER BY COALESCE(j.expired,0) ASC, COALESCE(j.match_score,0) DESC, j.created_at DESC LIMIT ?",
                (gates.AGENT3_CV_MIN_SCORE, gates.PIVOT_TRANSFERABILITY_FLOOR, limit),
            ).fetchall()
        elif stage == "leo":
            rows = conn.execute(
                "SELECT j.id AS id, j.job_title AS job_title, "
                "j.company_name AS company_name, j.match_score AS match_score "
                "FROM job_postings j "
                "JOIN company_dossiers d ON d.company_name = j.company_name "
                "WHERE j.match_score >= ? AND d.vetting_verdict = ? "
                "AND (j.cv_status IS NULL OR j.cv_status = '') "
                "ORDER BY COALESCE(j.expired,0) ASC, COALESCE(j.match_score,0) DESC, j.created_at DESC LIMIT ?",
                (gates.AGENT3_CV_MIN_SCORE, gates.AGENT3_CV_REQUIRED_VERDICT, limit),
            ).fetchall()
        elif stage == "clara":
            rows = conn.execute(
                "SELECT j.id AS id, j.job_title AS job_title, "
                "j.company_name AS company_name, j.match_score AS match_score "
                "FROM job_postings j "
                "WHERE j.match_score >= ? AND j.cv_status = ? "
                "AND (j.application_ready IS NULL OR j.application_ready = 0) "
                "ORDER BY COALESCE(j.expired,0) ASC, COALESCE(j.match_score,0) DESC, j.created_at DESC LIMIT ?",
                (gates.AGENT3_CV_MIN_SCORE, gates.STATUS_GENERATED, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, job_title, company_name, match_score FROM job_postings "
                "ORDER BY COALESCE(expired,0) ASC, COALESCE(match_score,0) DESC, created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "job_title": r["job_title"],
                "company_name": r["company_name"],
                "match_score": r["match_score"],
            }
            for r in rows
        ]
    finally:
        conn.close()


@app.get("/api/jobs/shelf", response_model=JobShelfResponse)
def jobs_shelf(limit: int = Query(200, ge=1, le=500)) -> JobShelfResponse:
    """Low-score, expired, and unconsiderable jobs — hidden from the kanban.

    Rows stay in job_postings so Rex/Milo can still retrieve them.
    # Ref: shelf_bucket exclusive categories
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM job_postings "
            "ORDER BY COALESCE(match_score, 0) DESC, created_at DESC"
        ).fetchall()
        lookup = _dossier_lookup(conn)
        buckets: dict[str, list[JobOut]] = {
            "low_score": [],
            "expired": [],
            "unconsiderable": [],
        }
        for row in rows:
            job = _attach_dossier(_row_to_job(row), lookup)
            bucket = gates.shelf_bucket(job.match_score, job.expired, job.user_status)
            if bucket:
                buckets[bucket].append(job)
        for key in buckets:
            buckets[key] = buckets[key][:limit]
        return JobShelfResponse(
            low_score=buckets["low_score"],
            expired=buckets["expired"],
            unconsiderable=buckets["unconsiderable"],
            counts={
                "low_score": len(buckets["low_score"]),
                "expired": len(buckets["expired"]),
                "unconsiderable": len(buckets["unconsiderable"]),
            },
        )
    finally:
        conn.close()


@app.get("/api/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int) -> JobOut:
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM job_postings WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(404, f"job {job_id} not found")
        lookup = _dossier_lookup(conn)
        return _attach_dossier(_row_to_job(row), lookup)
    finally:
        conn.close()


@app.patch("/api/jobs/{job_id}/status", response_model=JobOut)
def update_job_status(job_id: int, body: JobStatusUpdate) -> JobOut:
    """Expire / reactivate, or mark unconsiderable. Agents still see the row."""
    conn = _connect_rw()
    try:
        row = conn.execute("SELECT * FROM job_postings WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise HTTPException(404, f"job {job_id} not found")
        if body.expired is not None:
            conn.execute(
                "UPDATE job_postings SET expired = ? WHERE id = ?",
                (1 if body.expired else 0, job_id),
            )
        if body.unconsiderable is not None:
            status = (
                gates.USER_STATUS_UNCONSIDERABLE if body.unconsiderable else None
            )
            conn.execute(
                "UPDATE job_postings SET user_status = ? WHERE id = ?",
                (status, job_id),
            )
        conn.commit()
        row = conn.execute("SELECT * FROM job_postings WHERE id = ?", (job_id,)).fetchone()
        lookup = _dossier_lookup(conn)
        return _attach_dossier(_row_to_job(row), lookup)
    finally:
        conn.close()


@app.post("/api/jobs/{job_id}/check", response_model=JobCheckResult)
def check_job(job_id: int) -> JobCheckResult:
    """Check the source URL: HTTP status plus whether the stored title is on the page."""
    from listing_filters import listing_text_supports_title, listing_url_problem, normalize_listing_url

    conn = _connect()
    try:
        row = conn.execute(
            "SELECT job_url, job_title FROM job_postings WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"job {job_id} not found")
    finally:
        conn.close()
    url = normalize_listing_url(row["job_url"] or "")
    title = row["job_title"] or ""
    if not url:
        return JobCheckResult(exists=False, reason="no job_url", expired_suggested=True)
    shape = listing_url_problem(url)
    if shape:
        return JobCheckResult(
            exists=False,
            reason=shape,
            final_url=url,
            expired_suggested=True,
            listing_mismatch=True,
            title_found=False,
        )
    ok, status_code, final_url, reason, text = _fetch_job_page(url)
    if not ok:
        return JobCheckResult(
            exists=False,
            status_code=status_code,
            reason=reason,
            final_url=final_url,
            expired_suggested=True,
        )
    title_ok = listing_text_supports_title(text, title)
    if not title_ok:
        return JobCheckResult(
            exists=True,
            status_code=status_code,
            reason="page loaded but the stored job title is not on it",
            final_url=final_url,
            expired_suggested=True,
            listing_mismatch=True,
            title_found=False,
        )
    return JobCheckResult(
        exists=True,
        status_code=status_code,
        reason=reason,
        final_url=final_url,
        expired_suggested=False,
        listing_mismatch=False,
        title_found=True,
    )


def _safe_path(rel: Optional[str]) -> Optional[Path]:
    if not rel:
        return None
    p = Path(rel)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    try:
        p = p.resolve()
    except Exception:
        return None
    if not _under_project(p):
        return None
    return p if p.is_file() else None


def _dossier_markdown_file(out: CompanyDossierOut) -> Optional[Path]:
    """Resolve Dana's .md brief even when the DB stores a stale Windows path."""
    path = _safe_path(out.markdown_path)
    if path:
        return path
    folder = PROJECT_ROOT / "output" / "dossiers"
    if not folder.is_dir() or not out.company_name:
        return None
    token = re.split(r"[\s(/]", out.company_name.strip())[0]
    if len(token) < 3:
        return None
    needle = token.lower()
    for cand in sorted(folder.glob("*_Dossier.md")):
        if needle in cand.name.lower() and _under_project(cand):
            return cand.resolve()
    return None


def _candidate_display_name(candidate_id: Optional[str]) -> str:
    """basics.name from the selected profile, else a stable fallback.

    # Ref: CV download `{job_name}_{user_name}_cv.pdf`
    """
    cid = candidate_id or "default"
    try:
        path = _profile_path_for(cid)
    except HTTPException:
        path = DEFAULT_PROFILE
    if path.is_file():
        name = _profile_name(path)
        if name:
            return name
    return "Candidate"


@app.get("/api/jobs/{job_id}/cv")
def get_job_cv(
    job_id: int,
    download: bool = Query(False),
    candidate_id: Optional[str] = Query(None),
):
    from cv_filenames import cv_download_filename

    conn = _connect()
    try:
        row = conn.execute(
            "SELECT job_title, cv_pdf_path, cv_typ_path FROM job_postings WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "job not found")
    finally:
        conn.close()
    user_name = _candidate_display_name(candidate_id)
    job_title = row["job_title"] or "job"
    disposition = "attachment" if download else "inline"
    pdf = _safe_path(row["cv_pdf_path"])
    if pdf:
        return FileResponse(
            pdf,
            media_type="application/pdf",
            filename=cv_download_filename(job_title, user_name, "pdf"),
            content_disposition_type=disposition,
        )
    typ = _safe_path(row["cv_typ_path"])
    if typ:
        return FileResponse(
            typ,
            media_type="text/plain",
            filename=cv_download_filename(job_title, user_name, "typ"),
            content_disposition_type=disposition,
        )
    raise HTTPException(404, "no CV materials generated for this job yet")


@app.get("/api/jobs/{job_id}/checklist", response_class=HTMLResponse)
def get_job_checklist(job_id: int):
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT application_checklist_path FROM job_postings WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "job not found")
    finally:
        conn.close()
    path = _safe_path(row["application_checklist_path"])
    if not path:
        raise HTTPException(404, "no application checklist generated for this job yet")
    return HTMLResponse(markdown_to_html(path.read_text(encoding="utf-8")))


@app.get("/api/dossiers", response_model=list[CompanyDossierOut])
def list_dossiers(verdict: Optional[str] = Query(None)):
    conn = _connect()
    try:
        where = "WHERE d.vetting_verdict = ?" if verdict else ""
        params: list = [verdict] if verdict else []
        rows = conn.execute(
            "SELECT d.*, ("
            "  SELECT COUNT(*) FROM job_postings j "
            "  WHERE lower(trim(j.company_name)) = lower(trim(d.company_name))"
            ") AS job_count "
            f"FROM company_dossiers d {where} "
            "ORDER BY CASE WHEN d.confidence IS NULL THEN 1 ELSE 0 END, d.confidence DESC",
            params,
        ).fetchall()
        return [_row_to_dossier(r, job_count=int(r["job_count"] or 0)) for r in rows]
    finally:
        conn.close()


@app.get("/api/dossiers/{company_name}", response_model=CompanyDossierOut)
def get_dossier(company_name: str):
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM company_dossiers "
            "WHERE lower(trim(company_name)) = lower(trim(?))",
            (company_name,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"no dossier for {company_name}")
        jobs = _jobs_for_company(conn, row["company_name"])
        return _row_to_dossier(row, jobs=jobs)
    finally:
        conn.close()


@app.get("/api/dossiers/{company_name}/markdown", response_class=HTMLResponse)
def get_dossier_markdown(company_name: str):
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM company_dossiers "
            "WHERE lower(trim(company_name)) = lower(trim(?))",
            (company_name,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "no dossier")
        out = _row_to_dossier(row)
    finally:
        conn.close()
    path = _safe_path(out.markdown_path)
    if path:
        return HTMLResponse(markdown_to_html(path.read_text(encoding="utf-8")))
    md = _dossier_markdown_file(out)
    if md:
        return HTMLResponse(markdown_to_html(md.read_text(encoding="utf-8")))
    return HTMLResponse(markdown_to_html(_typed_dossier_markdown(out)))


@app.get("/api/jobs/{job_id}/dossier", response_model=CompanyDossierOut)
def get_job_dossier(job_id: int):
    conn = _connect()
    try:
        job = conn.execute("SELECT * FROM job_postings WHERE id = ?", (job_id,)).fetchone()
        if job is None:
            raise HTTPException(404, "job not found")
        row = _dossier_row_for_company(conn, job["company_name"])
        if row is None:
            raise HTTPException(404, "no dossier linked to this job")
        jobs = _jobs_for_company(conn, row["company_name"])
        return _row_to_dossier(row, jobs=jobs)
    finally:
        conn.close()


@app.get("/api/jobs/{job_id}/research", response_class=HTMLResponse)
def get_job_research(job_id: int):
    """Dana's Markdown brief for this job — job-id URL so the drawer iframe always loads."""
    conn = _connect()
    try:
        job = conn.execute("SELECT * FROM job_postings WHERE id = ?", (job_id,)).fetchone()
        if job is None:
            raise HTTPException(404, "job not found")
        row = _dossier_row_for_company(conn, job["company_name"])
        if row is None:
            raise HTTPException(404, "no dossier linked to this job")
        out = _row_to_dossier(row)
    finally:
        conn.close()
    path = _dossier_markdown_file(out)
    if path:
        return HTMLResponse(markdown_to_html(path.read_text(encoding="utf-8")))
    return HTMLResponse(markdown_to_html(_typed_dossier_markdown(out)))


@app.post("/api/agents/scout/run")
def run_scout(req: AgentRunRequest):
    return runner.start("rex", req)


@app.post("/api/agents/diligence/run")
def run_diligence(req: AgentRunRequest):
    return runner.start("dana", req)


@app.post("/api/agents/cv/run")
def run_cv(req: AgentRunRequest):
    return runner.start("leo", req)


@app.post("/api/agents/assembler/run")
def run_assembler(req: AgentRunRequest):
    return runner.start("clara", req)

@app.post("/api/agents/intake/run")
def run_intake(req: AgentRunRequest):
    return runner.start("milo", req)


@app.post("/api/agents/{agent_key}/stop")
def stop_agent(agent_key: str):
    if agent_key not in runner._rt:
        raise HTTPException(404, "unknown agent")
    return runner.stop(agent_key)


@app.get("/api/agents/status", response_model=AgentStatusMap)
def agents_status() -> AgentStatusMap:
    m = runner.status_all()
    return AgentStatusMap(
        milo=AgentStatus(**m["milo"]),
        rex=AgentStatus(**m["rex"]), dana=AgentStatus(**m["dana"]),
        leo=AgentStatus(**m["leo"]), clara=AgentStatus(**m["clara"]),
    )


# ---------------------------------------------------------------------------
# Pipeline — run all 5 agents in sequence (Milo → Rex → Dana → Leo → Clara)
# ---------------------------------------------------------------------------

@app.post("/api/pipeline/run")
def run_pipeline(req: AgentRunRequest):
    return runner.run_pipeline(req)


@app.post("/api/pipeline/stop")
def stop_pipeline():
    return runner.stop_pipeline()


@app.get("/api/pipeline/status")
def pipeline_status():
    return runner.pipeline_status()


def _read_log_tail(path: Path, tail: int) -> tuple[list[str], int]:
    """Read the last ``tail`` lines of ``path``. Returns (lines, total_lines).

    The unified log is append-only and small, so a full read + slice is fine.
    Returns ([], 0) if the file is missing or unreadable.

    # Ref: workspace rule — deterministic read helper, no LLM.
    """
    if not path.is_file():
        return [], 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            all_lines = fh.read().splitlines()
    except Exception:
        return [], 0
    total = len(all_lines)
    return all_lines[-tail:], total


@app.get("/api/agents/log")
def agents_log(
    tail: int = Query(500, ge=1, le=5000),
    source: Optional[str] = Query(None, description="Filter by source: Rex/Dana/Leo/Clara/SYSTEM"),
):
    """Tail of the unified cross-agent activity log (output/agent_activity.txt).

    When ``source`` is provided, returns only lines matching that source
    (parsed from the ``[SOURCE]`` tag in each log line). The file is still
    a single append-only .txt — filtering happens at read time, not write.
    """
    lines, total = _read_log_tail(LOG_FILE, tail)
    if source:
        source_upper = source.strip().upper()
        filtered = [
            line for line in lines
            if _parse_log_source(line) == source_upper
        ]
        return {
            "lines": filtered,
            "path": "output/agent_activity.txt",
            "total_lines": total,
            "filtered_total": len(filtered),
            "source": source_upper,
        }
    return {
        "lines": lines,
        "path": "output/agent_activity.txt",
        "total_lines": total,
    }


def _parse_log_source(line: str) -> str:
    """Extract the SOURCE from a log line ``[ts] [SOURCE] [LEVEL] msg``."""
    import re
    m = re.match(r"^\[[^\]]+\]\s*\[([^\]]+)\]", line or "")
    return m.group(1).upper() if m else ""


@app.get("/api/stats/funnel", response_model=FunnelStats)
def funnel() -> FunnelStats:
    conn = _connect()
    try:
        def count(sql, params=()):
            try:
                return int(conn.execute(sql, params).fetchone()[0])
            except Exception:
                return 0
        active_sql, active_params = _active_job_clause()
        found = count(
            f"SELECT COUNT(*) FROM job_postings WHERE {active_sql}",
            tuple(active_params),
        )
        score_ge_80 = count(
            f"SELECT COUNT(*) FROM job_postings WHERE {active_sql} AND match_score >= ?",
            tuple(active_params + [gates.AGENT3_CV_MIN_SCORE]),
        )
        vetted = count(
            "SELECT COUNT(DISTINCT company_name) FROM company_dossiers WHERE vetting_verdict = ?",
            (gates.AGENT3_CV_REQUIRED_VERDICT,),
        )
        cv_gen = count(
            "SELECT COUNT(*) FROM job_postings WHERE cv_status IN ('MATERIALS_GENERATED','MATERIALS_RENDERED')"
        )
        app_ready = count("SELECT COUNT(*) FROM job_postings WHERE application_ready = 1")
        return FunnelStats(
            found=found, score_ge_80=score_ge_80, vetted_proceed=vetted,
            cv_generated=cv_gen, application_ready=app_ready,
        )
    finally:
        conn.close()


@app.get("/api/gates")
def get_gates():
    return {
        "agent1_default_min_score": gates.AGENT1_DEFAULT_MIN_SCORE,
        "agent2_pool_min_score": gates.AGENT2_POOL_MIN_SCORE,
        "agent2_pool_transfer_floor": gates.AGENT2_POOL_TRANSFER_FLOOR,
        "agent3_cv_min_score": gates.AGENT3_CV_MIN_SCORE,
        "agent3_cv_required_verdict": gates.AGENT3_CV_REQUIRED_VERDICT,
        "agent4_min_score": gates.AGENT4_MIN_SCORE,
        "agent4_required_cv_status": gates.AGENT4_REQUIRED_CV_STATUS,
        "hard_weight": gates.HARD_WEIGHT,
        "transfer_weight": gates.TRANSFER_WEIGHT,
        "dashboard_min_display_score": gates.DASHBOARD_MIN_DISPLAY_SCORE,
        "user_status_unconsiderable": gates.USER_STATUS_UNCONSIDERABLE,
    }


# ---------------------------------------------------------------------------
# Scheduler — automated pipeline with Telegram notifications
# # Ref: APScheduler + cron triggers (default 9am + 6pm HKT)
# ---------------------------------------------------------------------------

@app.get("/api/scheduler/status")
def scheduler_status():
    from .scheduler import status as _status
    return _status()

@app.post("/api/scheduler/start")
def scheduler_start():
    from .scheduler import start as _start
    return _start()

@app.post("/api/scheduler/stop")
def scheduler_stop():
    from .scheduler import stop as _stop
    return _stop()

@app.post("/api/scheduler/run-now")
def scheduler_run_now():
    from .scheduler import run_now as _run_now
    return _run_now()

@app.post("/api/scheduler/configure")
def scheduler_configure(body: dict):
    from .scheduler import configure as _configure
    hours = body.get("hours", [9, 18])
    if not isinstance(hours, list) or not all(isinstance(h, int) for h in hours):
        raise HTTPException(400, "hours must be a list of integers")
    return _configure(hours)


# ---------------------------------------------------------------------------
# Profile-based suggestion tags (local Ollama gemma4:e2b, NOT DeepSeek)
# ---------------------------------------------------------------------------
# Rex gets HK job search queries; Dana gets target employer names. Both are
# generated from the candidate profile by a LOCAL Ollama model so nothing
# leaves the machine. If Ollama is unreachable, deterministic suggestions
# derived from the profile are returned instead — the endpoint never crashes.
# Ref: workspace rule — deterministic fallback separated from LLM; no cloud.

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma4:e2b"

# Canonical HK employers across the candidate's target domains
# (ConTech/PropTech, Critical Utilities, Logistics, FinTech). Mirrors the keys
# of HK_EMPLOYER_CAREER_SITES in src/agents/talent_scout_agent.py — kept inline
# here so the dashboard does not import the heavy agent module (openai/tavily).
# Ref: HK_EMPLOYER_CAREER_SITES registry
_FALLBACK_EMPLOYERS = [
    "MTR", "CLP", "ATAL", "Swire", "HSBC", "Cathay Pacific",
]


class SuggestionsOut(BaseModel):
    """Profile-based suggestion tags for Rex (queries) and Dana (employers)."""
    model_config = ConfigDict(extra="ignore")

    rex: list[str] = Field(default_factory=list)
    dana: list[str] = Field(default_factory=list)
    source: Literal["ollama", "fallback"] = "fallback"
    model: str = OLLAMA_MODEL


def _parse_suggestion_json(text: str) -> dict | None:
    """Parse Ollama JSON output, repairing common syntax errors. Never raises."""
    if not text:
        return None
    s = text.strip()
    # Strip surrounding code fences / prose if present.
    if s.startswith("```"):
        s = s.strip("`")
        # Drop a leading language tag like 'json'
        nl = s.find("\n")
        if nl > 0:
            s = s[nl:]
        s = s.strip("`").strip()
    try:
        payload = json.loads(s, strict=False)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    try:
        from json_repair import loads as json_repair_loads
        payload = json_repair_loads(s)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return None


def _ollama_suggest(profile: dict) -> dict | None:
    """Ask local Ollama gemma4:e2b for rex queries + dana employers.

    Returns ``{"rex": [...], "dana": [...]}`` or ``None`` if Ollama is
    unreachable / returns unparseable output. Never raises.
    """
    basics = profile.get("basics") or {}
    target_roles = basics.get("target_roles") or []
    tech = profile.get("technical_skills") or {}
    experience = profile.get("experience") or []
    exp_summary = [(e.get("role"), e.get("company")) for e in experience]

    prompt = (
        "Based on this candidate profile, suggest Hong Kong job search queries "
        "and target employers.\n"
        "Return ONLY a JSON object: "
        '{"rex": ["query1","query2",...], "dana": ["company1","company2",...]}\n\n'
        f"Profile:\n"
        f"- Target roles: {target_roles}\n"
        f"- Skills: {tech}\n"
        f"- Experience: {exp_summary}\n\n"
        "Generate 4-6 concise search queries for \"rex\" (Hong Kong job search "
        "strings tailored to the profile) and 4-6 Hong Kong employer names for "
        "\"dana\".\n"
    )
    try:
        r = httpx.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
            timeout=30.0,
        )
        r.raise_for_status()
        text = r.json().get("response", "")
        parsed = _parse_suggestion_json(text)
        if isinstance(parsed, dict):
            rex = [str(x) for x in (parsed.get("rex") or []) if x]
            dana = [str(x) for x in (parsed.get("dana") or []) if x]
            if rex or dana:
                return {"rex": rex, "dana": dana}
        return None
    except Exception:
        return None


def _fallback_suggest(profile: dict) -> dict:
    """Deterministic suggestions derived from the profile (Ollama down)."""
    basics = profile.get("basics") or {}
    target_roles = basics.get("target_roles") or []
    tech = profile.get("technical_skills") or {}

    # Rex: combine target roles with "Hong Kong", plus skill-flavoured queries.
    rex: list[str] = []
    for role in target_roles[:3]:
        rex.append(f"{role} Hong Kong")
    skill_pool: list[str] = []
    for group in tech.values():
        if isinstance(group, list):
            skill_pool.extend(str(s) for s in group)
    for sk in skill_pool[:3]:
        rex.append(f"{sk} engineer Hong Kong")
    seen: set[str] = set()
    rex_unique = [q for q in rex if not (q in seen or seen.add(q))]
    rex_out = rex_unique[:6] or ["Senior Backend Engineer Hong Kong"]

    # Dana: canonical HK employer registry keys.
    dana = list(_FALLBACK_EMPLOYERS)
    return {"rex": rex_out, "dana": dana}


@app.get("/api/suggestions", response_model=SuggestionsOut)
def suggestions(candidate_id: Optional[str] = Query(None)) -> SuggestionsOut:
    """Profile-based suggestion tags for Rex (queries) and Dana (employers).

    Calls local Ollama ``gemma4:e2b``; falls back to deterministic suggestions
    derived from the profile if Ollama is unreachable. The candidate profile
    is resolved the same way as ``agent_runner.resolve_profile_path``
    (config/profiles/{id}.json or config/master_profile.json).
    """
    profile_path = runner.resolve_profile_path(candidate_id)
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        profile = {}

    ollama = _ollama_suggest(profile)
    if ollama is not None:
        log_system("Suggestions generated via Ollama gemma4:e2b")
        return SuggestionsOut(
            rex=ollama.get("rex", []),
            dana=ollama.get("dana", []),
            source="ollama",
            model=OLLAMA_MODEL,
        )
    # Fallback: deterministic suggestions from the profile.
    fb = _fallback_suggest(profile)
    log_system(
        "Suggestions via fallback (Ollama gemma4:e2b unreachable)", level="WARN"
    )
    return SuggestionsOut(
        rex=fb["rex"], dana=fb["dana"], source="fallback", model=OLLAMA_MODEL,
    )


# ---------------------------------------------------------------------------
# Skill categories reference (job-platform-referenced) + per-category skill
# suggestions via local Ollama gemma4:e2b.
# ---------------------------------------------------------------------------
# Categories are NOT AI-generated — they come from config/skill_categories.json,
# a curated reference mapping HK job-platform categories (JobsDB, CTgoodjobs,
# LinkedIn) to the project's internal skill category names. The Tavily refresh
# is manual (user clicks a button), never automatic.
# Ref: workspace rule — deterministic config; LLM only for skill suggestions.

SKILL_CATEGORIES_PATH = PROJECT_ROOT / "config" / "skill_categories.json"
HK_TZ = timezone(timedelta(hours=8))


def _read_skill_categories() -> dict:
    """Read config/skill_categories.json. Returns empty structure if missing.

    # Ref: workspace rule — deterministic read helper, no LLM.
    """
    if not SKILL_CATEGORIES_PATH.is_file():
        return {"categories": [], "last_updated": None, "sources": []}
    try:
        data = json.loads(SKILL_CATEGORIES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {
                "categories": data.get("categories") or [],
                "last_updated": data.get("last_updated"),
                "sources": data.get("sources") or [],
            }
    except Exception:
        pass
    return {"categories": [], "last_updated": None, "sources": []}


@app.get("/api/skill-categories")
def get_skill_categories() -> dict:
    """Return the job-platform-referenced skill category list.

    # Ref: Task 2a — read config/skill_categories.json.
    """
    return _read_skill_categories()


# Regexes to extract category-like phrases from Tavily search-result text.
# Looks for patterns like "Information Technology — X", "IT — X", etc.
# Ref: workspace rule — deterministic extraction, no LLM guessing.
_CATEGORY_PATTERNS = [
    re.compile(r"Information Technology\s*[\-\u2013\u2014:]\s*([A-Za-z][A-Za-z\s/&]+)"),
    re.compile(r"\bIT\s*[\-\u2013\u2014:]\s*([A-Za-z][A-Za-z\s/&]+)"),
    re.compile(r"Engineering\s*[\-\u2013\u2014:]\s*([A-Za-z][A-Za-z\s/&]+)"),
    re.compile(r"Software Development\s*[\-\u2013\u2014:]\s*([A-Za-z][A-Za-z\s/&]+)"),
]


def _extract_categories_from_text(text: str) -> list[str]:
    """Extract category-like phrases from a blob of search-result text."""
    found: set[str] = set()
    if not text:
        return []
    for pat in _CATEGORY_PATTERNS:
        for m in pat.finditer(text):
            phrase = m.group(1).strip().rstrip(".,;:")
            if 2 <= len(phrase) <= 60:
                found.add(phrase)
    return sorted(found)


@app.post("/api/skill-categories/refresh")
def refresh_skill_categories() -> dict:
    """Refresh config/skill_categories.json via Tavily search of job platforms.

    Manual / on-demand only (user clicks the button). Merges any newly found
    category phrases into the existing reference without removing existing
    entries. Requires TAVILY_API_KEY.
    # Ref: Task 2b.
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise HTTPException(
            503,
            "TAVILY_API_KEY is not set — cannot refresh skill categories from job platforms.",
        )
    try:
        from tavily import TavilyClient
    except ImportError as exc:
        raise HTTPException(503, f"tavily package not installed: {exc}")

    queries = [
        "JobsDB Hong Kong job categories Information Technology 2026",
        "CTgoodjobs Hong Kong IT job categories list",
        "LinkedIn job function categories Information Technology",
    ]
    discovered: set[str] = set()
    try:
        client = TavilyClient(api_key=api_key)
        for q in queries:
            try:
                res = client.search(query=q, max_results=5)
                for r in (res.get("results") or []):
                    discovered.update(
                        _extract_categories_from_text(
                            (r.get("content") or "") + " " + (r.get("title") or "")
                        )
                    )
            except Exception:
                continue
    except Exception as exc:
        raise HTTPException(502, f"Tavily search failed: {exc}")

    # Merge with existing categories; never remove existing entries.
    current = _read_skill_categories()
    existing_names = {
        c.get("internal_name") for c in current["categories"] if isinstance(c, dict)
    }
    merged = list(current["categories"])
    for phrase in sorted(discovered):
        slug = phrase.lower().replace(" ", "_").replace("/", "_").replace("-", "_")
        slug = re.sub(r"[^a-z0-9_]", "", slug).strip("_")
        if slug and slug not in existing_names:
            existing_names.add(slug)
            merged.append({
                "internal_name": slug,
                "platform_labels": {"discovered": phrase},
                "description": phrase,
            })

    payload = {
        "last_updated": datetime.now(HK_TZ).isoformat(),
        "sources": current["sources"] or ["jobsdb", "ctgoodjobs", "linkedin"],
        "categories": merged,
    }
    try:
        SKILL_CATEGORIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        SKILL_CATEGORIES_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        raise HTTPException(500, f"failed to write skill_categories.json: {exc}")

    log_system("Skill categories refreshed via Tavily")
    return payload


def _profile_skill_context(profile: dict) -> dict:
    """Extract the skill-suggestion context from a profile dict.

    Returns target_roles, all existing skills across categories, experience
    highlights, and project tech stacks — the ground truth fed to Ollama.
    # Ref: workspace rule — deterministic extraction, no LLM.
    """
    basics = profile.get("basics") or {}
    target_roles = basics.get("target_roles") or []
    tech = profile.get("technical_skills") or {}
    all_existing: list[str] = []
    for group in tech.values():
        if isinstance(group, list):
            all_existing.extend(str(s) for s in group)
    experience = profile.get("experience") or []
    exp_highlights: list[str] = []
    for e in experience:
        if isinstance(e, dict):
            for h in (e.get("highlights") or []):
                exp_highlights.append(str(h))
    projects = profile.get("projects") or []
    project_tech: list[str] = []
    for p in projects:
        if isinstance(p, dict):
            for s in (p.get("tech_stack") or []):
                project_tech.append(str(s))
    return {
        "target_roles": target_roles,
        "all_existing_skills": all_existing,
        "experience_highlights": exp_highlights,
        "project_tech": project_tech,
    }


# --- Deterministic redundancy filter (post-Ollama) ---
# Ref: LLMs still produce semantically overlapping suggestions despite
# prompt rules. This pure function catches what the prompt misses.

# Skills that IMPLY a broader concept — if the candidate has the specific
# tool, the broader concept is redundant. Maps: broader_concept -> [specific tools that imply it]
_SKILL_IMPLICATIONS: dict[str, list[str]] = {
    "sql": ["postgresql", "postgres", "mysql", "sqlite", "mariadb", "mssql", "oracle", "cockroachdb", "tidb"],
    "relational database": ["postgresql", "postgres", "mysql", "sqlite", "mariadb", "mssql", "oracle"],
    "rdbms": ["postgresql", "postgres", "mysql", "sqlite", "mariadb", "mssql", "oracle"],
    "vector database": ["sqlite-vec", "lancedb", "pinecone", "weaviate", "chromadb", "milvus", "qdrant", "pgvector", "faiss"],
    "vector db": ["sqlite-vec", "lancedb", "pinecone", "weaviate", "chromadb", "milvus", "qdrant", "pgvector", "faiss"],
    "vector search": ["sqlite-vec", "lancedb", "pinecone", "weaviate", "chromadb", "milvus", "qdrant", "pgvector"],
    "time-series database": ["timescaledb", "influxdb", "prometheus", "clickhouse", "tdengine", "questdb"],
    "time series database": ["timescaledb", "influxdb", "prometheus", "clickhouse", "tdengine", "questdb"],
    "geospatial": ["postgis", "geopandas", "shapely", "gdal", "qgis"],
    "spatial database": ["postgis", "geopandas", "shapely"],
    "containerization": ["docker", "containerd", "podman", "cri-o"],
    "containers": ["docker", "containerd", "podman"],
    "rest api": ["fastapi", "flask", "django", "express", "spring boot", "gin", "echo"],
    "api design": ["fastapi", "flask", "django", "express", "spring boot", "openapi", "swagger"],
    "python web framework": ["fastapi", "flask", "django", "tornado", "bottle"],
    "python3": ["python"],
    "python programming": ["python"],
    "scripting": ["python", "bash", "powershell", "ruby"],
    "k8s": ["kubernetes"],
    "orchestration": ["kubernetes", "docker swarm", "nomad"],
    "ci/cd": ["github actions", "gitlab ci", "jenkins", "circleci", "argo cd", "tekton"],
    "machine learning": ["tensorflow", "pytorch", "scikit-learn", "keras", "litert", "onnx"],
    "ml framework": ["tensorflow", "pytorch", "scikit-learn", "keras"],
    "llm": ["langchain", "langgraph", "llamaindex", "haystack", "openai", "deepseek", "anthropic"],
    "ai agent": ["langgraph", "langchain", "crewai", "autogen", "mcp"],
    "embedding": ["fastembed", "openai", "sentence-transformers", "cohere"],
    "workflow automation": ["n8n", "node-red", "zapier", "make", "airflow", "prefect"],
    "edge computing": ["iot telemetry", "edge ai", "greengrass", "azure iot edge"],
}


def _normalize_skill(s: str) -> str:
    """Lowercase, replace parenthetical delimiters with spaces (keep content), collapse whitespace.

    Keeps parenthetical content so 'PostgreSQL (Spatial & Time-series optimization)'
    becomes 'postgresql spatial time-series optimization' — this ensures token
    overlap catches 'Time-series database' as redundant.
    """
    cleaned = re.sub(r"[\(\)]", " ", s or "")
    cleaned = re.sub(r"[/&\-]", " ", cleaned)  # split compound tokens
    return " ".join(cleaned.lower().split())


def _token_overlap(a: str, b: str) -> float:
    """Jaccard token overlap ratio between two normalized strings."""
    ta = set(a.split())
    tb = set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _is_redundant(suggestion: str, existing_skills: list[str]) -> bool:
    """Deterministic check: is `suggestion` redundant given `existing_skills`?

    Returns True if the suggestion is:
    - An exact or near-exact match (string similarity > 0.6)
    - A token subset of an existing skill
    - Shares 2+ consecutive tokens (bigram) with an existing skill
    - Implied by an existing skill via the implication map
    # Ref: workspace rule — deterministic logic separation
    """
    sug_norm = _normalize_skill(suggestion)
    if not sug_norm:
        return True

    sug_tokens = sug_norm.split()
    sug_bigrams = set(zip(sug_tokens, sug_tokens[1:]))

    for existing in existing_skills:
        ex_norm = _normalize_skill(existing)

        # 1. Exact match (normalized)
        if sug_norm == ex_norm:
            return True

        # 2. Substring check (either direction)
        if sug_norm in ex_norm or ex_norm in sug_norm:
            return True

        # 3. Token subset — if all suggestion tokens are in the existing skill
        ex_tokens = set(ex_norm.split())
        if sug_tokens and set(sug_tokens).issubset(ex_tokens):
            return True

        # 4. High token overlap (Jaccard > 0.4)
        if _token_overlap(sug_norm, ex_norm) > 0.4:
            return True

        # 5. Bigram overlap — shares 2+ consecutive tokens (e.g. "time series"
        #    in both "time series database" and "postgresql spatial time series optimization")
        ex_toks = ex_norm.split()
        ex_bigrams = set(zip(ex_toks, ex_toks[1:]))
        if sug_bigrams and ex_bigrams and len(sug_bigrams & ex_bigrams) >= 1:
            return True

        # 6. String similarity (SequenceMatcher ratio > 0.6)
        from difflib import SequenceMatcher
        ratio = SequenceMatcher(None, sug_norm, ex_norm).ratio()
        if ratio > 0.6:
            return True

    # 7. Implication map — if any existing skill implies the suggestion
    for implied_concept, specific_tools in _SKILL_IMPLICATIONS.items():
        # If the suggestion IS the broader concept (e.g., "SQL")
        # and the candidate has any specific tool that implies it (e.g., "PostgreSQL")
        if sug_norm == implied_concept or sug_norm.startswith(implied_concept):
            for existing in existing_skills:
                ex_norm = _normalize_skill(existing)
                for tool in specific_tools:
                    if tool in ex_norm:
                        return True

    return False


def _filter_redundant_skills(
    suggestions: list[str], existing_skills: list[str]
) -> list[str]:
    """Remove suggestions that are redundant given the candidate's existing skills.

    # Ref: deterministic post-filter — catches semantic overlap the LLM misses.
    """
    filtered: list[str] = []
    for sug in suggestions:
        if not _is_redundant(sug, existing_skills):
            # Also check against already-accepted suggestions (avoid internal dups)
            if not _is_redundant(sug, filtered):
                filtered.append(sug)
    return filtered


def _ollama_skill_suggest(profile: dict, category: str) -> list[str] | None:
    """Ask local Ollama gemma4:e2b for per-category skill suggestions.

    Returns a list of suggested skills, or ``None`` if Ollama is unreachable /
    returns unparseable output. Never raises. Uses the strict anti-duplicate
    prompt designed to ground suggestions in the candidate's evidence.
    # Ref: Task 2c — anti-duplicate prompt is the core of the request.
    """
    ctx = _profile_skill_context(profile)
    prompt = (
        f"You are a technical skills taxonomist for the Hong Kong IT job market.\n\n"
        f"Given the candidate's profile and a specific skill category, suggest NEW skill tags they should add.\n\n"
        f"STRICT RULES — violations make the output useless:\n"
        f"1. GROUND TRUTH: Suggest ONLY skills the candidate likely has, based on their experience highlights and project tech stacks. Do NOT invent skills they have no evidence of.\n"
        f"2. NO EXACT DUPLICATES: Do NOT suggest any skill already in the existing skills list.\n"
        f"3. NO SEMANTIC OVERLAP — THIS IS THE MOST IMPORTANT RULE:\n"
        f"   A suggestion is USELESS if it is implied by, a subset of, or a direct variant of any existing skill.\n"
        f"   Before outputting each suggestion, check it against EVERY existing skill:\n"
        f"   - If candidate has 'PostgreSQL', do NOT suggest 'SQL', 'Relational Database', 'RDBMS', or 'Postgres' — PostgreSQL IS a SQL database.\n"
        f"   - If candidate has 'sqlite-vec' or 'LanceDB', do NOT suggest 'Vector Database', 'Vector DB', or 'Vector Search' — those ARE vector databases.\n"
        f"   - If candidate has 'Docker', do NOT suggest 'Containerization' or 'Containers' — Docker IS containerization.\n"
        f"   - If candidate has 'FastAPI', do NOT suggest 'REST API', 'API Design', or 'Python Web Framework' — FastAPI IS a REST API framework.\n"
        f"   - If candidate has 'PostgreSQL (Spatial & Time-series optimization)', do NOT suggest 'Time-series Database', 'Geospatial Data', or 'Spatial Database' — those are already covered.\n"
        f"   - If candidate has 'Python', do NOT suggest 'Python3', 'Python Programming', or 'Scripting' — they are the same thing.\n"
        f"   - General rule: if suggestion X is a TYPE OF or IMPLIED BY any existing skill Y, then X is redundant. Remove it.\n"
        f"4. CATEGORY-BOUNDED: Suggestions must fit the category \"{category}\". Do not suggest frontend skills in a backend category.\n"
        f"5. MAX 6 suggestions. Quality over quantity. If fewer are justified, return fewer. It is BETTER to return 2 truly novel skills than 6 with overlap.\n"
        f"6. SPECIFIC & NOVEL: Each skill should be a useful, DISTINCT search tag that is NOT already covered. Prefer specific tools/frameworks the candidate used but hasn't listed yet (e.g., 'Redis' if they mention caching, 'Celery' if they mention async tasks).\n"
        f"7. Return ONLY valid JSON: {{\"skills\": [\"skill1\", \"skill2\", ...]}}\n\n"
        f"CANDIDATE PROFILE:\n"
        f"- Target roles: {ctx['target_roles']}\n"
        f"- Existing skills (ALL categories — do NOT repeat OR overlap with any of these): {ctx['all_existing_skills']}\n"
        f"- Experience highlights: {ctx['experience_highlights']}\n"
        f"- Project tech stacks: {ctx['project_tech']}\n\n"
        f"CATEGORY TO SUGGEST FOR: {category}\n"
    )
    try:
        r = httpx.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
            },
            timeout=30.0,
        )
        r.raise_for_status()
        text = r.json().get("response", "")
        parsed = _parse_suggestion_json(text)
        if isinstance(parsed, dict):
            skills = [str(s) for s in (parsed.get("skills") or []) if s]
            return skills
        return None
    except Exception:
        return None


@app.get("/api/skills/suggest")
def suggest_skills(
    candidate_id: Optional[str] = Query(None),
    category: str = Query(...),
) -> dict:
    """Per-category skill suggestions via local Ollama gemma4:e2b.

    Grounds suggestions in the candidate's experience highlights and project
    tech stacks, strictly avoiding duplicates of existing skills. Falls back
    to an empty list if Ollama is unreachable.
    # Ref: Task 2c — Ollama (local), NOT DeepSeek.
    """
    profile_path = _profile_path_for(candidate_id or "default")
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception:
        profile = {}

    ollama = _ollama_skill_suggest(profile, category)
    if ollama is not None:
        # Deterministic post-filter: remove suggestions that overlap with
        # existing skills (the LLM prompt catches most, but not all).
        ctx = _profile_skill_context(profile)
        existing = ctx["all_existing_skills"]
        filtered = _filter_redundant_skills(ollama, existing)
        removed = len(ollama) - len(filtered)
        if removed > 0:
            log_system(
                f"Skill suggestions for {category}: {len(filtered)} after "
                f"filtering {removed} redundant from {len(ollama)} raw"
            )
        else:
            log_system(f"Skill suggestions generated for category {category} via Ollama")
        return {"skills": filtered, "category": category, "source": "ollama"}
    log_system(
        f"Skill suggestions fallback for category {category} (Ollama unreachable)",
        level="WARN",
    )
    return {"skills": [], "category": category, "source": "fallback"}
