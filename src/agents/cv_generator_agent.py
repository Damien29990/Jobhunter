"""Agent 3 — Targeted CV Generator & Local Typst Compiler."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator, model_validator

AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from talent_scout_agent import (  # noqa: E402
    DEFAULT_DB_PATH,
    DEFAULT_PROFILE_PATH,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_CHAT_MODEL,
    HK_TZ,
    PROJECT_ROOT,
    JobDBManager,
    parse_json_payload,
)

_VALIDATORS_DIR = Path(__file__).resolve().parent.parent / "validators"
if str(_VALIDATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS_DIR))

from llm_usage import finalize_usage, instrument_openai  # noqa: E402
from activity_logger import log_activity  # noqa: E402
from cv_canvas import (  # noqa: E402
    list_canvas_templates,
    pick_canvas_template,
)
from milo_context import milo_readme_prompt_block  # noqa: E402
from notify import notify_job_update  # noqa: E402
from cv_filenames import cover_letter_filename, cv_download_filename  # noqa: E402
from cv_experience import iter_experience_roles  # noqa: E402
from contact_links import contact_plain_lines, contact_typst_markup  # noqa: E402
from cv_projects import select_and_order_cv_projects  # noqa: E402

TEMPLATES_DIR = PROJECT_ROOT / "templates"
OUTPUT_DIR = PROJECT_ROOT / "output"
RESUME_TEMPLATE_NAME = "resume.typ.j2"
COVER_LETTER_TEMPLATE_NAME = "cover_letter.typ.j2"
MIN_MATCH_SCORE = 80
PROCEED_VERDICT = "PROCEED"
STATUS_GENERATED = "MATERIALS_GENERATED"
STATUS_RENDERED = "MATERIALS_RENDERED"
STATUS_FAILED = "GENERATION_FAILED"
TYPST_SPECIAL = ("#", "$", "*", "_", "<", ">", "@", "\\", "[", "]")


class TailoredExperience(BaseModel):
    company: str
    role: str
    period: str
    highlights: List[str]


class TailoredProject(BaseModel):
    name: str
    description: str
    tech_stack: List[str]
    role: str = ""
    is_side_project: bool = False
    period: str = ""
    employer: str = ""


class TailoredCoverLetter(BaseModel):
    """Cover letter grounded in the same master profile as the CV.

    # Ref: Agent 3 application documents
    """

    greeting: str = "Dear Hiring Manager,"
    paragraphs: List[str] = Field(default_factory=list)
    closing: str = "Yours sincerely,"

    @field_validator("paragraphs")
    @classmethod
    def clip_paragraphs(cls, value: List[str]) -> List[str]:
        rows = [str(item).strip() for item in (value or []) if str(item).strip()]
        return rows[:4]


class TailoredCVPayload(BaseModel):
    """DeepSeek structured output for a tailored CV. Ground truth only.

    # Ref: Agent 3 data contract
    """

    target_company: str
    target_role: str
    professional_summary: str = Field(
        description="2-3 sentence executive summary aligning candidate with JD"
    )
    prioritized_skills: Dict[str, List[str]] = Field(
        description="Categorized skills with JD-relevant technologies first"
    )
    experience: List[TailoredExperience]
    projects: List[TailoredProject] = Field(
        description="2-4 JD-relevant projects from the master profile, work projects before side projects"
    )
    certifications: List[str]
    cover_letter: TailoredCoverLetter = Field(default_factory=TailoredCoverLetter)

    @field_validator("prioritized_skills")
    @classmethod
    def coerce_skills(cls, value: Dict[str, List[str]]) -> Dict[str, List[str]]:
        cleaned: Dict[str, List[str]] = {}
        for category, items in (value or {}).items():
            if isinstance(items, str):
                items = [items]
            cleaned[str(category)] = [str(i) for i in items if str(i).strip()]
        return cleaned

    @model_validator(mode="after")
    def require_targets(self) -> "TailoredCVPayload":
        if not self.target_company.strip():
            raise ValueError("target_company must not be empty")
        if not self.target_role.strip():
            raise ValueError("target_role must not be empty")
        return self


def apply_cv_project_selection(
    payload: TailoredCVPayload,
    jd_text: str,
) -> TailoredCVPayload:
    """Clip to 2-4 JD-relevant projects; side projects last.

    # Ref: src/validators/cv_projects.py
    """
    rows = [item.model_dump() for item in payload.projects]
    picked = select_and_order_cv_projects(rows, jd_text or "")
    payload.projects = [TailoredProject.model_validate(item) for item in picked]
    return payload


def loads_llm_json_object(raw: str) -> dict:
    """Parse DeepSeek JSON, repairing common syntax errors."""
    text = parse_json_payload(raw)
    try:
        payload = json.loads(text, strict=False)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    try:
        from json_repair import loads as json_repair_loads

        payload = json_repair_loads(text)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    raise ValueError("LLM output is not a JSON object")


def coerce_cv_payload(raw: str, target_company: str, target_role: str) -> dict:
    """Fill aliases so a missing field does not drop the whole CV."""
    payload = loads_llm_json_object(raw)
    payload.setdefault("target_company", target_company)
    payload.setdefault("target_role", target_role)
    payload.setdefault("professional_summary", "")
    payload.setdefault("prioritized_skills", {})
    payload.setdefault("experience", [])
    payload.setdefault("projects", [])
    payload.setdefault("certifications", [])
    if "skills" in payload and not payload["prioritized_skills"]:
        skills = payload["skills"]
        if isinstance(skills, dict):
            payload["prioritized_skills"] = skills
        elif isinstance(skills, list):
            payload["prioritized_skills"] = {"Technical": skills}
    if "summary" in payload and not payload["professional_summary"]:
        payload["professional_summary"] = payload["summary"]
    for key in ("experience", "projects"):
        if isinstance(payload.get(key), dict):
            payload[key] = [payload[key]]
    rows = payload.get("projects")
    if isinstance(rows, list):
        cleaned: List[dict] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            item.setdefault("role", "")
            item.setdefault("is_side_project", False)
            item.setdefault("period", "")
            item.setdefault("employer", "")
            item.setdefault("description", "")
            item.setdefault("tech_stack", [])
            cleaned.append(item)
        payload["projects"] = cleaned
    payload["cover_letter"] = coerce_cover_letter(payload.get("cover_letter"))
    return payload


def coerce_cover_letter(raw: object) -> dict:
    """Accept a string or object so a missing cover letter does not drop the CV."""
    default = {
        "greeting": "Dear Hiring Manager,",
        "paragraphs": [],
        "closing": "Yours sincerely,",
    }
    if isinstance(raw, str) and raw.strip():
        default["paragraphs"] = [raw.strip()]
        return default
    if not isinstance(raw, dict):
        return default
    greeting = str(raw.get("greeting") or default["greeting"]).strip() or default["greeting"]
    closing = str(raw.get("closing") or default["closing"]).strip() or default["closing"]
    paras = raw.get("paragraphs")
    if isinstance(paras, str) and paras.strip():
        rows = [paras.strip()]
    elif isinstance(paras, list):
        rows = [str(item).strip() for item in paras if str(item).strip()]
    else:
        rows = []
    body = str(raw.get("body") or "").strip()
    if body and not rows:
        rows = [body]
    return {"greeting": greeting, "paragraphs": rows[:4], "closing": closing}


def cover_letter_markdown(
    candidate_name: str,
    payload: TailoredCVPayload,
    letter_date: str,
    basics: Optional[dict] = None,
) -> str:
    """Plain-text cover letter for email / ATS paste boxes.

    # Ref: Agent 3 application documents
    """
    letter = payload.cover_letter
    contact = contact_plain_lines(basics or {})
    blocks = [
        candidate_name,
        *contact,
        letter_date,
        "",
        payload.target_company,
        payload.target_role,
        "",
        letter.greeting,
        "",
        *letter.paragraphs,
        "",
        letter.closing,
        "",
        candidate_name,
        "",
    ]
    return "\n".join(blocks)


def typ_escape(text: object) -> str:
    """Escape Typst special characters so profile text renders literally.

    # Ref: Typst markup reserves — # $ * _ < > @ \
    """
    if text is None:
        return ""
    out: List[str] = []
    for ch in str(text):
        if ch in TYPST_SPECIAL:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def make_jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(disabled_extensions=("j2", "typ.j2"), default=False),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["typ_escape"] = typ_escape
    return env


def safe_stem(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name or "")
    cleaned = " ".join(cleaned.split())
    return (cleaned[:80] or "company").rstrip(" .")


def typst_available() -> bool:
    try:
        result = subprocess.run(
            ["typst", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def compile_typst_resume(typst_source_path: Path, output_pdf_path: Path) -> bool:
    """Compile a .typ source file to PDF via the local Typst CLI."""
    return compile_typst_with_error(typst_source_path, output_pdf_path)[0]


def compile_typst_with_error(typst_source_path: Path, output_pdf_path: Path) -> tuple[bool, str]:
    """Compile .typ to PDF. Returns (success, error_text).

    # Ref: LangGraph cyclic self-correction — error_text feeds back to LLM.
    """
    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["typst", "compile", str(typst_source_path), str(output_pdf_path)]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        print(f"📄 PDF successfully compiled: {output_pdf_path}")
        return True, ""
    except subprocess.CalledProcessError as exc:
        error = exc.stderr or exc.stdout or "unknown error"
        print(f"❌ Typst compilation failed: {error[:200]}")
        return False, error
    except FileNotFoundError:
        print("❌ Typst CLI not found. Install: winget install --id Typst.Typst")
        return False, "Typst CLI not found"


def language_labels(profile: dict) -> List[str]:
    """Display strings for the CV Languages section."""
    items = profile.get("languages")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        labels: List[str] = []
        for item in items:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            level = str(item.get("proficiency") or "").strip()
            labels.append(f"{name} ({level})" if level else name)
        if labels:
            return labels
    basics = profile.get("basics") or {}
    return [str(x) for x in (basics.get("languages") or []) if str(x).strip()]


def award_labels(profile: dict) -> List[str]:
    """Display strings for the CV Awards section."""
    rows: List[str] = []
    for item in profile.get("awards") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        issuer = str(item.get("issuer") or "").strip()
        year = item.get("year")
        extra = " ".join(part for part in (issuer, str(year) if year not in (None, "") else "") if part)
        rows.append(f"{name} ({extra})" if extra else name)
    return rows


def load_master_profile(path: Path = DEFAULT_PROFILE_PATH) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"master_profile.json not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("master_profile.json must be a JSON object")
    return raw


def profile_brief(profile: dict) -> str:
    """Compact ground-truth context for the tailoring LLM."""
    basics = profile.get("basics") or {}
    experience: list[dict] = []
    for item in profile.get("experience") or []:
        company = item.get("company")
        for stint in iter_experience_roles(item):
            experience.append({
                "company": company,
                "role": stint.get("role"),
                "period": stint.get("period"),
                "highlights": stint.get("highlights") or [],
                "skills_used": stint.get("skills_used") or [],
            })
    projects = [
        {
            "name": item.get("name"),
            "role": item.get("role") or "",
            "is_side_project": bool(item.get("is_side_project")),
            "period": item.get("period") or "",
            "employer": item.get("employer") or "",
            "description": item.get("description"),
            "tech_stack": item.get("tech_stack") or [],
        }
        for item in (profile.get("projects") or [])
    ]
    certifications = [
        f"{item.get('name')} ({item.get('issuer')}, {item.get('year')})"
        for item in (profile.get("certifications") or [])
    ]
    return json.dumps(
        {
            "name": basics.get("name"),
            "email": basics.get("email"),
            "phone": basics.get("phone"),
            "address": basics.get("address"),
            "website": basics.get("website"),
            "github": basics.get("github"),
            "linkedin": basics.get("linkedin"),
            "target_roles": basics.get("target_roles"),
            "languages": language_labels(profile),
            "min_expected_salary_hkd": basics.get("min_expected_salary_hkd"),
            "technical_skills": profile.get("technical_skills") or {},
            "experience": experience,
            "projects": projects,
            "certifications": certifications,
            "awards": award_labels(profile),
            "education": profile.get("education") or [],
        },
        ensure_ascii=False,
    )


class CVGeneratorAgent:
    """Tailor resumes for vetted high-match jobs and compile them with Typst."""

    def __init__(
        self,
        deepseek_api_key: str,
        db_path: str = DEFAULT_DB_PATH,
        profile_path: Path = DEFAULT_PROFILE_PATH,
        template_name: str = RESUME_TEMPLATE_NAME,
        canvas_template_id: Optional[str] = None,
    ):
        self.chat_model = os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_CHAT_MODEL)
        self.client = instrument_openai(
            OpenAI(api_key=deepseek_api_key, base_url=DEEPSEEK_BASE_URL)
        )
        self.db_manager = JobDBManager(db_path=db_path)
        self.profile_path = profile_path
        self.template_name = template_name
        self.canvas_template_id = (canvas_template_id or "").strip() or None
        self.jinja_env = make_jinja_env()
        self.master_profile = load_master_profile(profile_path)
        self._typst_ok = typst_available()
        if not self._typst_ok:
            print(
                "⚠️  Typst CLI not on PATH — .typ source will still be written; "
                "PDF compilation will be skipped. Install: winget install --id Typst.Typst"
            )

    def list_vetted_jobs(self, min_score: int = MIN_MATCH_SCORE) -> List[dict]:
        """Jobs with match_score >= min_score whose dossier verdict is PROCEED.

        # Ref: Agent 3 gate — high match AND vetting_verdict = PROCEED
        """
        cursor = self.db_manager.db.execute(
            """
            SELECT
                j.id, j.job_url, j.job_title, j.company_name,
                j.jd_snippet, j.match_score, j.recommendation_reason,
                j.cv_status, d.dossier_json, d.vetting_verdict
            FROM job_postings j
            LEFT JOIN company_dossiers d
              ON LOWER(TRIM(j.company_name)) = LOWER(TRIM(d.company_name))
            WHERE j.match_score >= ?
              AND COALESCE(d.vetting_verdict, '') = ?
              AND NOT (
                    COALESCE(j.cv_status, '') IN (?, ?)
                    AND (
                      COALESCE(j.cover_letter_typ_path, '') != ''
                      OR COALESCE(j.cover_letter_pdf_path, '') != ''
                    )
                  )
            ORDER BY j.match_score DESC
            """,
            (min_score, PROCEED_VERDICT, STATUS_GENERATED, STATUS_RENDERED),
        )
        rows: List[dict] = []
        for row in cursor.fetchall():
            rows.append(
                {
                    "id": row[0],
                    "job_url": row[1],
                    "job_title": row[2],
                    "company_name": row[3],
                    "jd_snippet": row[4] or "",
                    "match_score": row[5],
                    "recommendation_reason": row[6],
                    "cv_status": row[7],
                    "dossier_json": row[8],
                    "vetting_verdict": row[9],
                }
            )
        return rows

    def fetch_job(self, job_id: int) -> Optional[dict]:
        """Load one job for a targeted Leo re-run, including already-generated rows."""
        cursor = self.db_manager.db.execute(
            """
            SELECT
                j.id, j.job_url, j.job_title, j.company_name,
                j.jd_snippet, j.match_score, j.recommendation_reason,
                j.cv_status, d.dossier_json, d.vetting_verdict
            FROM job_postings j
            LEFT JOIN company_dossiers d
              ON LOWER(TRIM(j.company_name)) = LOWER(TRIM(d.company_name))
            WHERE j.id = ?
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "job_url": row[1],
            "job_title": row[2],
            "company_name": row[3],
            "jd_snippet": row[4] or "",
            "match_score": row[5],
            "recommendation_reason": row[6],
            "cv_status": row[7],
            "dossier_json": row[8],
            "vetting_verdict": row[9],
        }

    def _dossier_summary(self, job: dict) -> str:
        dossier_json = job.get("dossier_json")
        if not dossier_json:
            return ""
        try:
            dossier = json.loads(dossier_json)
        except json.JSONDecodeError:
            return ""
        if not isinstance(dossier, dict):
            return ""
        return (
            f"Verdict: {dossier.get('vetting_verdict', PROCEED_VERDICT)}\n"
            f"Tech stack: {', '.join(dossier.get('detected_tech_stack') or [])}\n"
            f"Culture: {dossier.get('engineering_culture', '')}\n"
            f"Advisory: {dossier.get('career_advisory_note', '')}"
        )

    def tailor_cv(self, job: dict, dossier_summary: str = "", compile_error: str = "") -> Optional[TailoredCVPayload]:
        """Ask DeepSeek to align the master profile with this JD.

        If compile_error is provided, the previous Typst source failed to compile.
        The error is fed back to the LLM for self-correction.
        # Ref: ground truth enforcement — no fabrication; cyclic self-correction.
        """
        schema = json.dumps(TailoredCVPayload.model_json_schema(), ensure_ascii=False)
        system_prompt = f"""
You are an expert Technical Career Strategist and ATS Optimization Specialist.
Tailor the candidate's master profile to align with the provided Job Description (JD) and Company Dossier.

Strict Rules:
1. Ground Truth Enforcement: Use ONLY facts, metrics, and tools present in the master profile. NEVER fabricate degrees, employers, or technologies not present in the source profile.
2. ATS Alignment: Prioritize matching frameworks, databases, and architectural patterns (e.g., IoT telemetry, high-throughput time-series PostgreSQL, React full-stack, AI agents).
3. STAR Method: Reword existing bullet points to emphasize impact, architecture, and quantifiable outcomes.
4. Output must be a single valid JSON object matching the TailoredCVPayload schema.
5. JSON hygiene: escape inner quotes; no trailing commas; no markdown fences; keep each string under 280 characters; keep each list at most 8 items.
6. prioritized_skills must be a JSON object mapping category name to a list of skill strings, with JD-relevant technologies placed first.
7. experience must come from the master profile only — do not invent new employers.
8. Copy each project's role, is_side_project, period, and employer from the master profile. Do not relabel a side project as employment.
9. projects: select 2-4 JD-relevant projects only. Do NOT copy every project. Prefer employment/work projects (is_side_project=false). Include a side project only if it strongly matches the JD and you still have fewer than 4. Order work projects first; side projects last.
10. Also fill cover_letter: 2-4 short paragraphs in professional Hong Kong English for this company and role. Greeting is "Dear Hiring Manager," unless the JD names a contact. Closing is "Yours sincerely,". Use only facts from the master profile. Do not invent salary, visa status, years of experience, or certifications. Mention 2-3 JD-relevant strengths that exist in the profile.

JSON Schema:
{schema}
"""
        user_prompt = (
            f"Target company: {job['company_name']}\n"
            f"Target role: {job['job_title']}\n\n"
            f"JOB DESCRIPTION:\n{job['jd_snippet'][:6000]}\n\n"
            f"COMPANY DOSSIER SUMMARY:\n{dossier_summary[:3000]}\n\n"
            f"MASTER PROFILE (ground truth):\n{profile_brief(self.master_profile)}"
            f"{milo_readme_prompt_block(self.profile_path)}"
        )
        if compile_error:
            user_prompt += (
                f"\n\n⚠️ PREVIOUS TYPOST COMPILE ERROR (fix the syntax that caused this):\n{compile_error}\n"
                f"Regenerate the CV JSON ensuring the content will compile cleanly in Typst. "
                f"Escape special characters: # $ * _ < > @ \\ [ ]"
            )
        try:
            response = self.client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
        except Exception as exc:
            print(f"⚠️  [DeepSeek call failed] {job['company_name']}: {exc}")
            return None
        raw = response.choices[0].message.content
        if not raw:
            return None
        try:
            payload = TailoredCVPayload.model_validate(
                coerce_cv_payload(raw, job["company_name"], job["job_title"])
            )
            return apply_cv_project_selection(payload, job.get("jd_snippet") or "")
        except Exception as exc:
            print(f"⚠️  [JSON parse skipped] {job['company_name']}: {exc}")
            return None

    def render_typst_source(
        self,
        payload: TailoredCVPayload,
        template_file: Optional[str] = None,
    ) -> str:
        """Render a Canvas (or default) Jinja2 template to Typst source."""
        basics = self.master_profile.get("basics") or {}
        education = self.master_profile.get("education") or []
        languages = language_labels(self.master_profile)
        awards = award_labels(self.master_profile)
        name = template_file or self.template_name
        template = self.jinja_env.get_template(name)
        return template.render(
            candidate_name=basics.get("name") or "Candidate",
            contact_line=contact_typst_markup(basics),
            professional_summary=payload.professional_summary,
            prioritized_skills=payload.prioritized_skills,
            experience=[item.model_dump() for item in payload.experience],
            projects=[item.model_dump() for item in payload.projects],
            certifications=payload.certifications,
            awards=awards,
            education=education,
            languages=languages,
        )

    def render_cover_letter_source(self, payload: TailoredCVPayload) -> str:
        """Render the cover-letter Jinja2 template to Typst source."""
        basics = self.master_profile.get("basics") or {}
        letter = payload.cover_letter
        template = self.jinja_env.get_template(COVER_LETTER_TEMPLATE_NAME)
        return template.render(
            candidate_name=basics.get("name") or "Candidate",
            contact_line=contact_typst_markup(basics),
            letter_date=datetime.now(HK_TZ).strftime("%d %B %Y"),
            company_name=payload.target_company,
            target_role=payload.target_role,
            greeting=letter.greeting,
            paragraphs=letter.paragraphs,
            closing=letter.closing,
        )

    def _write_cover_letter(
        self,
        payload: TailoredCVPayload,
        out_dir: Path,
        job_title: str,
        user_name: str,
    ) -> dict:
        """Write cover letter .typ / .md / optional PDF. CV status is independent.

        # Ref: Agent 3 related documents — cover letter must not fail the CV.
        """
        result: dict = {"typ_path": None, "pdf_path": None, "md_path": None}
        if not payload.cover_letter.paragraphs:
            print("⏭️  Cover letter skipped — LLM returned empty paragraphs.")
            return result
        typ_path = out_dir / cover_letter_filename(job_title, user_name, "typ")
        typ_path.write_text(self.render_cover_letter_source(payload), encoding="utf-8")
        result["typ_path"] = str(typ_path)
        print(f"✉️  Cover letter Typst written: {typ_path}")
        log_activity("Leo", f"Cover letter Typst written: {typ_path}")

        md_path = out_dir / cover_letter_filename(job_title, user_name, "md")
        md_body = cover_letter_markdown(
            candidate_name=str((self.master_profile.get("basics") or {}).get("name") or "Candidate"),
            payload=payload,
            letter_date=datetime.now(HK_TZ).strftime("%d %B %Y"),
            basics=self.master_profile.get("basics") or {},
        )
        md_path.write_text(md_body, encoding="utf-8")
        result["md_path"] = str(md_path)

        pdf_path = out_dir / cover_letter_filename(job_title, user_name, "pdf")
        if self._typst_ok:
            compiled, error = compile_typst_with_error(typ_path, pdf_path)
            if compiled:
                result["pdf_path"] = str(pdf_path)
                log_activity("Leo", f"Cover letter PDF compiled: {pdf_path}")
            else:
                log_activity(
                    "Leo",
                    f"Cover letter Typst compile failed (CV still kept): {error[:200]}",
                    level="WARN",
                )
        return result

    def _update_status(
        self,
        job_id: int,
        status: str,
        pdf_path: Optional[str] = None,
        typ_path: Optional[str] = None,
        cover_letter_pdf_path: Optional[str] = None,
        cover_letter_typ_path: Optional[str] = None,
    ) -> None:
        with self.db_manager.db:
            self.db_manager.db.execute(
                """
                UPDATE job_postings
                SET cv_status = ?,
                    cv_pdf_path = COALESCE(?, cv_pdf_path),
                    cv_typ_path = COALESCE(?, cv_typ_path),
                    cover_letter_pdf_path = COALESCE(?, cover_letter_pdf_path),
                    cover_letter_typ_path = COALESCE(?, cover_letter_typ_path)
                WHERE id = ?
                """,
                (
                    status,
                    pdf_path,
                    typ_path,
                    cover_letter_pdf_path,
                    cover_letter_typ_path,
                    job_id,
                ),
            )

    def generate_for_job(
        self,
        job: dict,
        documents: Optional[frozenset[str]] = None,
    ) -> Optional[dict]:
        """Tailor → render → compile → update DB status for one job.

        documents=None writes CV and cover letter. Pass frozenset({"cv"}) or
        frozenset({"cover_letter"}) to rebuild one file only.
        """
        write_cv = documents is None or "cv" in documents
        write_letter = documents is None or "cover_letter" in documents
        company = job["company_name"]
        title = job["job_title"]
        print(f"\n🧵 [Tailoring CV] {company} — {title} (match={job['match_score']})")
        log_activity(
            "Leo",
            f"Tailoring {'CV' if write_cv else ''}{' + ' if write_cv and write_letter else ''}{'cover letter' if write_letter else ''} for {company} — {title}",
        )

        payload = self.tailor_cv(job, dossier_summary=self._dossier_summary(job))
        if not payload:
            if write_cv:
                self._update_status(job["id"], STATUS_FAILED)
            return None
        last_payload = payload
        layout = pick_canvas_template(
            jd_text=job.get("jd_snippet") or "",
            job_title=job.get("job_title") or "",
            forced_id=self.canvas_template_id,
        )
        print(f"🎨 [Canvas] {layout.name} ({layout.id}) ← {layout.file}")
        log_activity("Leo", f"Canvas template {layout.id}: {layout.name}")
        log_activity("Leo", "DeepSeek returned payload, rendering Typst")

        out_dir = OUTPUT_DIR / f"{safe_stem(company)}_{safe_stem(title)}"
        out_dir.mkdir(parents=True, exist_ok=True)
        user_name = str((self.master_profile.get("basics") or {}).get("name") or "Candidate")
        typ_path = out_dir / cv_download_filename(title, user_name, "typ")
        pdf_path = out_dir / cv_download_filename(title, user_name, "pdf")
        compiled = False

        if write_cv:
            typ_source = self.render_typst_source(payload, template_file=layout.file)
            typ_path.write_text(typ_source, encoding="utf-8")
            print(f"📝 Typst source written: {typ_path}")
            log_activity("Leo", f"Typst source written: {typ_path}")
            compile_error = ""
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                if self._typst_ok:
                    compiled, compile_error = compile_typst_with_error(typ_path, pdf_path)
                    if compiled:
                        log_activity("Leo", f"PDF compiled: {pdf_path}")
                        break
                    if attempt < max_retries:
                        print(f"🔄 [Typst retry {attempt}/{max_retries}] Feeding compile error back to DeepSeek…")
                        log_activity("Leo", f"Typst compile failed (attempt {attempt}), retrying with error feedback", level="WARN")
                        payload = self.tailor_cv(
                            job,
                            dossier_summary=self._dossier_summary(job),
                            compile_error=compile_error[:500],
                        )
                        if payload:
                            last_payload = payload
                            typ_source = self.render_typst_source(
                                payload, template_file=layout.file
                            )
                            typ_path.write_text(typ_source, encoding="utf-8")
                            print(f"📝 Typst source re-written (attempt {attempt + 1}): {typ_path}")
                        else:
                            break
                    else:
                        log_activity("Leo", f"Max retries ({max_retries}) reached, marking failed", level="ERROR")
                else:
                    print("⏭️  [Typst CLI missing] PDF skipped; .typ source is available.")
                    break

        if write_cv:
            status = STATUS_GENERATED if compiled else (
                STATUS_RENDERED if typ_path.exists() else STATUS_FAILED
            )
        else:
            status = job.get("cv_status") or STATUS_RENDERED

        cover_paths: dict = {"typ_path": None, "pdf_path": None, "md_path": None}
        if write_letter:
            cover_paths = self._write_cover_letter(
                last_payload, out_dir, title, user_name
            )
        self._update_status(
            job["id"],
            status=status,
            pdf_path=str(pdf_path) if write_cv and compiled else None,
            typ_path=str(typ_path) if write_cv else None,
            cover_letter_pdf_path=cover_paths.get("pdf_path") if write_letter else None,
            cover_letter_typ_path=cover_paths.get("typ_path") if write_letter else None,
        )
        log_activity("Leo", f"DB updated: cv_status={status} for job #{job['id']}")
        notify_job_update(
            "Leo",
            f"CV {status}",
            company=company,
            title=title,
            url=job.get("job_url") or "",
            extra=str(pdf_path) if write_cv and compiled else (
                cover_paths.get("pdf_path") or cover_paths.get("typ_path") or str(typ_path)
            ),
        )
        return {
            "job_id": job["id"],
            "company": company,
            "title": title,
            "typ_path": str(typ_path) if write_cv else None,
            "pdf_path": str(pdf_path) if write_cv and compiled else None,
            "cover_letter_typ_path": cover_paths.get("typ_path"),
            "cover_letter_pdf_path": cover_paths.get("pdf_path"),
            "status": status,
        }

    def run_pipeline(
        self,
        min_score: int = MIN_MATCH_SCORE,
        job_id: Optional[int] = None,
        company: Optional[str] = None,
        force: bool = False,
        document: str = "all",
    ) -> int:
        """Generate tailored CVs for all vetted high-match jobs."""
        kind = (document or "all").strip().lower()
        docs: Optional[frozenset[str]]
        if kind == "cv":
            docs = frozenset({"cv"})
        elif kind == "cover_letter":
            docs = frozenset({"cover_letter"})
        else:
            docs = None
        jobs: List[dict] = []
        if job_id is not None:
            loaded = self.fetch_job(job_id)
            if loaded:
                jobs = [loaded]
                score = int(loaded.get("match_score") or 0)
                if score < min_score:
                    print(
                        f"ℹ️  [Manual] job #{job_id} composite={score} "
                        f"< min {min_score}; generating anyway"
                    )
                    log_activity(
                        "Leo",
                        f"Score gate bypassed for job #{job_id} (composite={score})",
                    )
        else:
            jobs = self.list_vetted_jobs(min_score=min_score)
        if company:
            key = company.strip().lower()
            jobs = [j for j in jobs if key in (j["company_name"] or "").lower()]
        if not jobs:
            print(
                "ℹ️  No new vetted jobs. Need match_score >= "
                f"{min_score} and verdict PROCEED, still missing a CV or cover letter "
                "(or pass --job-id to generate for one listing)."
            )
            return 0
        print(f"📋 {len(jobs)} vetted job(s) queued for CV generation.")
        catalog = list_canvas_templates()
        if catalog:
            names = ", ".join(f"{t.id} ({t.name})" for t in catalog)
            print(f"🎨 Canvas templates: {names}")
        generated = 0
        for job in jobs:
            result = self.generate_for_job(job, documents=docs)
            if result and result["status"] in (STATUS_GENERATED, STATUS_RENDERED):
                generated += 1
                tag = "PDF" if result["pdf_path"] else ".typ only"
                print(f"✅ [{tag}] {result['company']} — {result['title']}")
        print(f"\n✅ 申請文件生成完成！處理 {len(jobs)} 份職缺，成功 {generated} 份。")
        log_activity("Leo", f"Pipeline complete: {generated} CV + cover letter pack(s)")
        notify_job_update(
            "Leo",
            "Application materials finished",
            extra=f"{generated} CV + cover letter pack(s) written",
        )
        return generated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Targeted CV Generator & Typst Compiler")
    parser.add_argument("--job-id", type=int, default=None, help="Generate CV only for this job id")
    parser.add_argument("--company", default=None, help="Filter jobs by company name substring")
    parser.add_argument("--min-score", type=int, default=MIN_MATCH_SCORE)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild materials even if this job already has a CV / cover letter",
    )
    parser.add_argument(
        "--document",
        choices=("all", "cv", "cover_letter"),
        default="all",
        help="Rebuild only CV, only cover letter, or both",
    )
    parser.add_argument(
        "--template",
        default=None,
        help="Force a Canvas template id (classic, compact, technical)",
    )
    parser.add_argument(
        "--list-templates",
        action="store_true",
        help="Print Leo's Canvas catalog and exit",
    )
    args = parser.parse_args()

    if args.list_templates:
        for item in list_canvas_templates():
            print(f"{item.id}\t{item.file}\t{item.name} — {item.when}")
        raise SystemExit(0)

    load_dotenv(PROJECT_ROOT / ".env")
    from env_keys import deepseek_api_key
    deepseek_key = deepseek_api_key()
    if not deepseek_key:
        raise SystemExit("Set DEEPSEEK_API_KEY in the environment or a .env file.")
    print(f"Using DeepSeek {os.environ.get('DEEPSEEK_MODEL', DEEPSEEK_CHAT_MODEL)} @ {DEEPSEEK_BASE_URL}")
    agent = CVGeneratorAgent(
        deepseek_api_key=deepseek_key,
        canvas_template_id=args.template,
    )
    agent.run_pipeline(
        min_score=args.min_score,
        job_id=args.job_id,
        company=args.company,
        force=args.force,
        document=args.document,
    )
    finalize_usage("Leo")
