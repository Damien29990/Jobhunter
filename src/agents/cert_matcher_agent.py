"""Agent 4 — Certificate Matcher & Application Readiness Auditor.

Audits high-match jobs whose CV is already generated, matches the candidate's
REAL credentials (ground truth only) to the role, detects the application
channel (Workday / Greenhouse / JobsDB / LinkedIn / Direct Email), and exports
an Application Hand-in Checklist as Markdown.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
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
    PROJECT_ROOT,
    JobDBManager,
    extract_host,
    is_ats_host,
    parse_json_payload,
)

from activity_logger import log_activity  # noqa: E402
from llm_usage import finalize_usage, instrument_openai  # noqa: E402
from milo_context import milo_readme_prompt_block  # noqa: E402
from notify import notify_job_update  # noqa: E402

OUTPUT_DIR = PROJECT_ROOT / "output"
MIN_MATCH_SCORE = 80
STATUS_GENERATED = "MATERIALS_GENERATED"  # Agent 3 gate: CV already produced

# Friendly channel names keyed by the first alphabetic run of the host.
# Ref: ATS host classification — Workday / Greenhouse / JobsDB / LinkedIn
_CHANNEL_ALIASES = {
    "workday": "Workday",
    "greenhouse": "Greenhouse",
    "successfactors": "SuccessFactors",
    "jobsdb": "JobsDB",
    "ctgoodjobs": "CTgoodjobs",
    "linkedin": "LinkedIn",
    "lever": "Lever",
    "smartrecruiters": "SmartRecruiters",
}

# Detect a "send your CV to hr@example.com" hint in the JD body.
_EMAIL_HINT_RE = re.compile(
    r"(?i)(?:e-?mail|email|電郵|電子郵件)\s*[:：]?\s*[\w.+-]+@[\w.-]+\.[a-z]{2,}"
)


# ---------------------------------------------------------------------------
# 1. Pydantic data models
# ---------------------------------------------------------------------------

class MatchedCredential(BaseModel):
    """One candidate credential mapped to a concrete application talking point.

    # Ref: Agent 4 data contract — ground-truth credentials only, no fabrication
    """

    credential_name: str = Field(
        description="Name of candidate certification, degree, or language proficiency"
    )
    category: str = Field(description="Cloud / Safety / Language / Degree")
    relevance_to_role: str = Field(
        description="Actionable rationale for why this credential supports the target role"
    )
    recommended_action: str = Field(
        description="Attach PDF / Mention in CV header / State in online form field"
    )


class PortalSubmissionAudit(BaseModel):
    """Portal-specific submission audit for one job.

    # Ref: Agent 4 data contract — application mechanism + screening traps
    """

    application_channel: str = Field(
        description="Workday / Greenhouse / JobsDB / Direct Email / Company Portal"
    )
    submission_target: str = Field(
        description="Direct URL or recipient HR email address"
    )
    required_documents: List[str] = Field(
        description="Explicitly demanded files (e.g. Tailored CV, Cover Letter, Portfolio/Demo)"
    )
    optional_documents: List[str] = Field(
        description="Suggested enhancers (e.g. AWS Certificate PDF, St. John First Aid Card, GitHub Link)"
    )
    form_screening_traps: List[str] = Field(
        description="Known portal-specific questions (e.g. Expected Salary, Notice Period, Visa / HK Permanent Residency status)"
    )
    special_submission_instructions: str = Field(
        description="Specific instructions found in the JD (e.g. 'Quote Ref: CES in email subject')"
    )

    @field_validator("application_channel")
    @classmethod
    def normalize_channel(cls, value: str) -> str:
        key = re.sub(r"[^a-z]", "", (value or "").lower())
        if key in _CHANNEL_ALIASES:
            return _CHANNEL_ALIASES[key]
        return (value or "").strip() or "Company Portal"

    @field_validator("required_documents", "optional_documents", "form_screening_traps")
    @classmethod
    def coerce_doc_lists(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()]


class ApplicationReadinessPack(BaseModel):
    """Full readiness pack: audit + matched credentials + action items.

    # Ref: Agent 4 data contract — orchestrates the final human submission
    """

    company_name: str
    job_title: str
    job_url: str
    submission_audit: PortalSubmissionAudit
    matched_credentials: List[MatchedCredential]
    demo_recommendation: Optional[str] = Field(
        default=None,
        description="Whether a code demo / micro-repo is recommended for this job and what it should showcase",
    )
    final_human_action_items: List[str] = Field(
        description="Step-by-step checklist for the candidate before clicking submit"
    )

    @field_validator("matched_credentials", "final_human_action_items")
    @classmethod
    def coerce_lists(cls, value):
        if value is None:
            return []
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return value
        return [value]

    @model_validator(mode="after")
    def require_targets(self) -> "ApplicationReadinessPack":
        if not (self.company_name or "").strip():
            raise ValueError("company_name must not be empty")
        if not (self.job_title or "").strip():
            raise ValueError("job_title must not be empty")
        if not (self.job_url or "").strip():
            raise ValueError("job_url must not be empty")
        return self


# ---------------------------------------------------------------------------
# 2. JSON parsing & coercion helpers (same pattern as cv_generator_agent)
# ---------------------------------------------------------------------------

def loads_llm_json_object(raw: str) -> dict:
    """Parse DeepSeek JSON, repairing common syntax errors via json_repair."""
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


def coerce_readiness_payload(
    raw: str, company_name: str, job_title: str, job_url: str
) -> dict:
    """Fill aliases/defaults so a missing field does not drop the whole pack."""
    payload = loads_llm_json_object(raw)
    payload.setdefault("company_name", company_name)
    payload.setdefault("job_title", job_title)
    payload.setdefault("job_url", job_url)
    payload.setdefault("submission_audit", {})
    payload.setdefault("matched_credentials", [])
    payload.setdefault("demo_recommendation", None)
    payload.setdefault("final_human_action_items", [])

    audit = payload["submission_audit"]
    if isinstance(audit, str):
        audit = {"application_channel": audit, "submission_target": job_url}
    if isinstance(audit, dict):
        audit.setdefault("application_channel", "Company Portal")
        audit.setdefault("submission_target", job_url)
        audit.setdefault("required_documents", [])
        audit.setdefault("optional_documents", [])
        audit.setdefault("form_screening_traps", [])
        audit.setdefault("special_submission_instructions", "")
    payload["submission_audit"] = audit

    # Alias tolerance: LLM sometimes nests credentials under a different key.
    for alt in ("credentials", "matched_creds", "talking_points"):
        if alt in payload and not payload["matched_credentials"]:
            payload["matched_credentials"] = payload[alt]
    for alt in ("action_items", "checklist", "final_action_items"):
        if alt in payload and not payload["final_human_action_items"]:
            payload["final_human_action_items"] = payload[alt]

    return payload


# ---------------------------------------------------------------------------
# 3. Deterministic helpers (no LLM guessing)
# ---------------------------------------------------------------------------

def safe_stem(name: str) -> str:
    """Filesystem-safe stem, matching cv_generator_agent.safe_stem."""
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name or "")
    cleaned = " ".join(cleaned.split())
    return (cleaned[:80] or "company").rstrip(" .")


def jd_mentions_email(jd_text: str) -> bool:
    """True when the JD body contains an HR-style email contact hint."""
    return bool(_EMAIL_HINT_RE.search(jd_text or ""))


def load_master_profile(path: Path = DEFAULT_PROFILE_PATH) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"master_profile.json not found: {path}")
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("master_profile.json must be a JSON object")
    return raw


def credentials_brief(profile: dict) -> str:
    """Compact ground-truth credential context for the audit LLM.

    Only real facts from master_profile.json are emitted — the LLM is told not
    to fabricate. # Ref: ground-truth enforcement
    """
    basics = profile.get("basics") or {}
    certifications = [
        {
            "name": item.get("name"),
            "issuer": item.get("issuer"),
            "year": item.get("year"),
            "category": item.get("category"),
        }
        for item in (profile.get("certifications") or [])
    ]
    education = [
        {
            "institution": item.get("institution"),
            "degree": item.get("degree"),
            "year": item.get("year"),
        }
        for item in (profile.get("education") or [])
    ]
    return json.dumps(
        {
            "name": basics.get("name"),
            "languages": basics.get("languages") or [],
            "certifications": certifications,
            "education": education,
            "technical_skills": profile.get("technical_skills") or {},
        },
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# 4. CertMatcherAgent
# ---------------------------------------------------------------------------

class CertMatcherAgent:
    """Match real credentials to roles and audit the application mechanism."""

    def __init__(
        self,
        deepseek_api_key: str,
        db_path: str = DEFAULT_DB_PATH,
        profile_path: Path = DEFAULT_PROFILE_PATH,
    ):
        self.chat_model = os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_CHAT_MODEL)
        self.client = instrument_openai(
            OpenAI(api_key=deepseek_api_key, base_url=DEEPSEEK_BASE_URL)
        )
        self.db_manager = JobDBManager(db_path=db_path)
        self.profile_path = profile_path
        self.master_profile = load_master_profile(profile_path)

    # -- queue ---------------------------------------------------------------

    def list_ready_jobs(self, min_score: int = MIN_MATCH_SCORE) -> List[dict]:
        """Jobs with match_score >= min_score whose CV is already generated.

        # Ref: Agent 4 gate — match_score >= min_score AND cv_status = MATERIALS_GENERATED
        """
        cursor = self.db_manager.db.execute(
            """
            SELECT id, job_url, job_title, company_name, jd_snippet,
                   match_score, cv_pdf_path, cv_typ_path
            FROM job_postings
            WHERE match_score >= ?
              AND cv_status = ?
            ORDER BY match_score DESC
            """,
            (min_score, STATUS_GENERATED),
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
                    "cv_pdf_path": row[6],
                    "cv_typ_path": row[7],
                }
            )
        return rows

    # -- deterministic channel detection --------------------------------------

    def detect_application_channel(self, job_url: str, jd_text: str) -> dict:
        """Deterministic pre-hint: classify the application channel from the URL host.

        The LLM still makes the final call; this just provides a strong hint so
        the auditor does not have to re-derive Workday/Greenhouse/JobsDB from
        scratch. # Ref: ATS host classification — Workday / Greenhouse / JobsDB
        """
        host = extract_host(job_url)
        parsed = urlparse(job_url if "://" in job_url else f"https://{job_url}")
        path = parsed.path.lower()

        channel = "Company Portal"
        if "myworkdayjobs.com" in host:
            channel = "Workday"
        elif "greenhouse.io" in host:
            channel = "Greenhouse"
        elif "successfactors.com" in host or "successfactors.eu" in host:
            channel = "SuccessFactors"
        elif "jobsdb.com" in host:
            channel = "JobsDB"
        elif "ctgoodjobs.hk" in host:
            channel = "CTgoodjobs"
        elif "linkedin.com" in host and "/jobs" in path:
            channel = "LinkedIn"
        elif "lever.co" in host:
            channel = "Lever"
        elif "smartrecruiters.com" in host:
            channel = "SmartRecruiters"
        elif not is_ats_host(host) and jd_mentions_email(jd_text):
            # Non-ATS host with an HR email in the JD → direct email application.
            channel = "Direct Email"

        return {"channel": channel, "submission_target": job_url}

    # -- LLM audit -----------------------------------------------------------

    def audit_job(self, job: dict, channel_hint: dict) -> Optional[ApplicationReadinessPack]:
        """Ask DeepSeek to audit the JD + URL and match real credentials.

        # Ref: ground-truth enforcement — credentials come from master_profile only
        """
        schema = json.dumps(
            ApplicationReadinessPack.model_json_schema(), ensure_ascii=False
        )
        system_prompt = f"""
You are a Hong Kong IT career strategist and ATS submission auditor.
Audit the Job Description (JD) and the job URL for the application mechanism,
then match the candidate's REAL credentials to the role and produce an
Application Hand-in Checklist.

Strict Rules:
1. Ground Truth Enforcement: Use ONLY credentials present in the candidate
   profile below (AWS SAA, St. John First Aid, JLPT N3, PolyU EIE BSc, and the
   listed languages). NEVER fabricate certifications, degrees, or language
   proficiencies that are not in the profile.
2. Credential talking points must be concrete and actionable, e.g.:
   - "AWS SAA validates cloud microservices architecture and cost-resilient design."
   - "St. John First Aid confirms site/safety compliance for ConTech or field roles."
   - "JLPT N3 enables collaboration with JP-headquartered teams and JP vendor docs."
   - "PolyU EIE BSc covers embedded systems, signal processing, and full-stack engineering."
3. Application channel: a deterministic hint is provided. Use it as the
   primary signal but correct it if the JD clearly states otherwise (e.g. an
   email address in the JD body overrides a generic Company Portal hint).
4. required_documents: only files the JD explicitly demands. optional_documents:
   suggested enhancers drawn from the candidate's real credentials (e.g. AWS
   Certificate PDF, St. John First Aid Card, GitHub link).
5. form_screening_traps: portal-specific questions to prepare for (Expected
   Salary, Notice Period, Visa / HK Permanent Residency status, etc.).
6. special_submission_instructions: any verbatim instruction in the JD (e.g.
   "Quote Ref: CES in email subject", "apply via company portal only").
7. demo_recommendation: if the role is backend / IoT / AI, recommend a small
   code demo or micro-repo and state what it should showcase (time-series,
   edge telemetry, agent orchestration). Otherwise leave it null.
8. BILINGUAL OUTPUT: Write submission_audit.special_submission_instructions, form_screening_traps, matched_credentials (relevance_to_role, recommended_action), demo_recommendation, and final_human_action_items in BOTH English and Traditional Chinese. Format: "English. 繁體中文。" Each list item bilingual.
9. final_human_action_items: ordered step-by-step checklist the candidate
   follows before clicking submit (attach PDFs, fill portal fields, etc.).
10. Output must be a single valid JSON object matching the
   ApplicationReadinessPack schema. No markdown fences.
11. JSON hygiene: escape every double-quote inside strings; no trailing
    commas; keep each string under 280 characters; keep each list at most
    8 items.

JSON Schema:
{schema}
"""
        user_prompt = (
            f"Company: {job['company_name']}\n"
            f"Role: {job['job_title']}\n"
            f"Job URL: {job['job_url']}\n"
            f"Application channel hint: {channel_hint['channel']} "
            f"(submission target: {channel_hint['submission_target']})\n\n"
            f"JOB DESCRIPTION:\n{job['jd_snippet'][:6000]}\n\n"
            f"CANDIDATE CREDENTIALS (ground truth, do not fabricate):\n"
            f"{credentials_brief(self.master_profile)}"
            f"{milo_readme_prompt_block(self.profile_path)}"
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
            payload = coerce_readiness_payload(
                raw, job["company_name"], job["job_title"], job["job_url"]
            )
            return ApplicationReadinessPack.model_validate(payload)
        except Exception as exc:
            print(f"⚠️  [JSON parse skipped] {job['company_name']}: {exc}")
            return None

    # -- markdown export -----------------------------------------------------

    def render_checklist_markdown(self, pack: ApplicationReadinessPack) -> str:
        """Render the Application Hand-in Checklist as Markdown.

        # Ref: Agent 4 output format — Application_Checklist.md
        """
        audit = pack.submission_audit

        def _checkbox(items) -> str:
            cleaned = [str(i).strip() for i in (items or []) if str(i).strip()]
            return "\n".join(f"- [ ] {item}" for item in cleaned) or "- [ ] (none listed)"

        def _traps(items) -> str:
            cleaned = [str(i).strip() for i in (items or []) if str(i).strip()]
            return "\n".join(f"- ⚠️ {item}" for item in cleaned) or "- (none flagged)"

        creds_md = []
        for cred in pack.matched_credentials:
            creds_md.append(
                f"### {cred.credential_name} ({cred.category})\n"
                f"- **Relevance:** {cred.relevance_to_role}\n"
                f"- **Action:** {cred.recommended_action}"
            )
        creds_section = "\n\n".join(creds_md) if creds_md else "_No credentials matched._"

        demo = pack.demo_recommendation or "No code demo required for this role."

        actions = pack.final_human_action_items or []
        if actions:
            actions_section = "\n".join(
                f"{i}. {item}" for i, item in enumerate(actions, 1)
            )
        else:
            actions_section = "_No action items recorded._"

        return f"""# {pack.company_name} — Application Hand-in Checklist

**Role:** {pack.job_title}
**Job URL:** {pack.job_url}
**Application Channel:** {audit.application_channel}
**Submission Target:** {audit.submission_target}

## Required Documents
{_checkbox(audit.required_documents)}

## Optional / Enhancer Documents
{_checkbox(audit.optional_documents)}

## Form Screening Traps
{_traps(audit.form_screening_traps)}

## Special Submission Instructions
{audit.special_submission_instructions or "(none stated in the JD)"}

## Matched Credentials & Talking Points
{creds_section}

## Demo Recommendation
{demo}

## Final Human Action Items
{actions_section}
"""

    def export_checklist(self, pack: ApplicationReadinessPack) -> Path:
        """Write the checklist to output/{company}_{title}/Application_Checklist.md."""
        out_dir = OUTPUT_DIR / f"{safe_stem(pack.company_name)}_{safe_stem(pack.job_title)}"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "Application_Checklist.md"
        path.write_text(self.render_checklist_markdown(pack), encoding="utf-8")
        return path

    # -- DB status update ----------------------------------------------------

    def _update_status(
        self, job_id: int, application_ready: bool, checklist_path: Optional[str]
    ) -> None:
        with self.db_manager.db:
            self.db_manager.db.execute(
                """
                UPDATE job_postings
                SET application_ready = ?,
                    application_checklist_path = COALESCE(?, application_checklist_path)
                WHERE id = ?
                """,
                (1 if application_ready else 0, checklist_path, job_id),
            )

    # -- orchestration -------------------------------------------------------

    def generate_for_job(self, job: dict) -> Optional[dict]:
        """detect → audit → render → export → update DB for one job."""
        company = job["company_name"]
        title = job["job_title"]
        print(f"\n🧾 [Auditing application] {company} — {title} (match={job['match_score']})")
        log_activity(
            "Clara",
            f"Auditing application readiness for {company} — {title}",
        )

        channel_hint = self.detect_application_channel(job["job_url"], job["jd_snippet"])
        print(f"   channel hint → {channel_hint['channel']}")
        log_activity(
            "Clara",
            f"Detected channel: {channel_hint['channel']} → {channel_hint['submission_target']}",
        )

        pack = self.audit_job(job, channel_hint)
        if not pack:
            self._update_status(job["id"], False, None)
            return None
        log_activity(
            "Clara",
            f"Audit complete: {len(pack.matched_credentials)} credentials matched for {company}",
        )

        checklist_path = self.export_checklist(pack)
        print(f"📝 Checklist written: {checklist_path}")
        log_activity("Clara", f"Checklist exported: {checklist_path}")
        self._update_status(job["id"], True, str(checklist_path))
        log_activity(
            "Clara",
            f"DB updated: application_ready=True for job #{job['id']}",
        )
        notify_job_update(
            "Clara",
            "Application ready",
            company=company,
            title=title,
            url=job.get("job_url") or "",
            extra=pack.submission_audit.application_channel,
        )
        return {
            "job_id": job["id"],
            "company": company,
            "title": title,
            "channel": pack.submission_audit.application_channel,
            "checklist_path": str(checklist_path),
            "application_ready": True,
        }

    def run_pipeline(
        self,
        min_score: int = MIN_MATCH_SCORE,
        job_id: Optional[int] = None,
        company: Optional[str] = None,
    ) -> int:
        """Audit application readiness for all jobs whose CV is already generated."""
        jobs = self.list_ready_jobs(min_score=min_score)
        if job_id is not None:
            jobs = [j for j in jobs if j["id"] == job_id]
        if company:
            key = company.strip().lower()
            jobs = [j for j in jobs if key in (j["company_name"] or "").lower()]
        if not jobs:
            print(
                "ℹ️  No ready jobs found. Need job_postings.match_score >= "
                f"{min_score} with cv_status = 'MATERIALS_GENERATED'."
            )
            return 0
        print(f"📋 {len(jobs)} ready job(s) queued for application audit.")
        audited = 0
        for job in jobs:
            result = self.generate_for_job(job)
            if result and result["application_ready"]:
                audited += 1
                print(f"✅ [Ready] {result['company']} — {result['title']} [{result['channel']}]")
        print(f"\n✅ 申請準備審計完成！處理 {len(jobs)} 份職缺，成功 {audited} 份。")
        log_activity("Clara", f"Pipeline complete: {audited} checklists generated")
        notify_job_update(
            "Clara",
            "Jobs finished",
            extra=f"{audited} application pack(s) ready",
        )
        return audited


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Certificate Matcher & Application Readiness Auditor"
    )
    parser.add_argument(
        "--job-id", type=int, default=None, help="Audit only this job id"
    )
    parser.add_argument(
        "--company", default=None, help="Filter jobs by company name substring"
    )
    parser.add_argument("--min-score", type=int, default=MIN_MATCH_SCORE)
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    from env_keys import deepseek_api_key
    deepseek_key = deepseek_api_key()
    if not deepseek_key:
        raise SystemExit("Set DEEPSEEK_API_KEY in the environment or a .env file.")
    print(f"Using DeepSeek {os.environ.get('DEEPSEEK_MODEL', DEEPSEEK_CHAT_MODEL)} @ {DEEPSEEK_BASE_URL}")
    agent = CertMatcherAgent(deepseek_api_key=deepseek_key)
    agent.run_pipeline(min_score=args.min_score, job_id=args.job_id, company=args.company)
    finalize_usage("Clara")
