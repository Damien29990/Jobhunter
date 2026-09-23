"""Pydantic v2 response models for the dashboard API.

Strict typing, no Any. JSON columns (matched_skills, missing_skills,
transferable_strengths, dossier_json, source_urls) are parsed into typed
objects on the API side — the client never parses DB JSON.
# Ref: workspace rule — Pydantic v2, 禁用 Any; Asia/Hong_Kong ISO 8601 timestamps.
"""
from __future__ import annotations

import json
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SourceLane = Literal[
    "hk_job_boards", "ats_platforms", "hk_employer_careers", "target_employer"
]
TargetIndustry = Literal[
    "ConTech", "PropTech", "Critical Utilities", "Logistics", "FinTech"
]
CvStatus = Literal[
    "MATERIALS_GENERATED", "MATERIALS_RENDERED", "GENERATION_FAILED"
]
Verdict = Literal["PROCEED", "AVOID"]
ApplicationChannel = Literal[
    "Workday", "Greenhouse", "SuccessFactors", "JobsDB", "CTgoodjobs",
    "LinkedIn", "Lever", "SmartRecruiters", "Direct Email", "Company Portal",
]
AgentState = Literal["IDLE", "WORKING", "FAILED"]


def _parse_json_list(value) -> list[str]:
    """Coerce a TEXT(JSON) column into list[str]. Never raises."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s, strict=False)
        except Exception:
            return []
        if isinstance(parsed, list):
            return [str(v) for v in parsed if v is not None]
        if isinstance(parsed, str):
            return [parsed]
        return []
    return []


def _parse_text_list(value) -> list[str]:
    """Coerce Agent 2 list-or-string fields (news, flags, questions, URLs).

    # Ref: due_diligence_agent.CompanyDueDiligence — recent_news_and_events is List[str]
    A plain paragraph that is not JSON is kept as a single item, not dropped.
    """
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s, strict=False)
        except Exception:
            return [s]
        if isinstance(parsed, list):
            return [str(v).strip() for v in parsed if v is not None and str(v).strip()]
        if isinstance(parsed, str) and parsed.strip():
            return [parsed.strip()]
        return [s]
    return [str(value).strip()] if str(value).strip() else []


class JobOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    job_url: str
    company_name: Optional[str] = None
    job_title: str
    source_domain: Optional[str] = None
    source_lane: Optional[str] = None
    location_mode: Optional[str] = None
    salary_range: Optional[str] = None
    match_score: Optional[int] = None
    hard_skill_match_score: Optional[int] = None
    transferability_score: Optional[int] = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    transferable_strengths: list[str] = Field(default_factory=list)
    is_direct_hire: Optional[bool] = None
    recommendation_reason: Optional[str] = None
    jd_snippet: Optional[str] = None
    target_industry: Optional[str] = None
    career_advisory_note: Optional[str] = None
    cv_status: Optional[str] = None
    cv_pdf_path: Optional[str] = None
    cv_typ_path: Optional[str] = None
    cover_letter_pdf_path: Optional[str] = None
    cover_letter_typ_path: Optional[str] = None
    application_ready: Optional[bool] = None
    application_checklist_path: Optional[str] = None
    expired: Optional[bool] = None  # dashboard-managed expiry flag
    user_status: Optional[str] = None
    unconsiderable: bool = False
    created_at: Optional[str] = None
    dossier: Optional["CompanyDossierOut"] = None  # Dana brief; set by the API, not a DB column

    @field_validator(
        "matched_skills", "missing_skills", "transferable_strengths", mode="before"
    )
    @classmethod
    def _coerce_lists(cls, v):
        return _parse_json_list(v)

    @field_validator("application_ready", "expired", mode="before")
    @classmethod
    def _coerce_bool(cls, v):
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v == 1
        if isinstance(v, str):
            return v.strip() in ("1", "true", "True", "TRUE")
        return bool(v)

    @model_validator(mode="after")
    def _derive_unconsiderable(self) -> "JobOut":
        status = (self.user_status or "").strip().upper()
        self.unconsiderable = status == "UNCONSIDERABLE"
        return self


class DossierPayload(BaseModel):
    """Parsed CompanyDueDiligence JSON (Agent 2 distillation).

    # Ref: due_diligence_agent.CompanyDueDiligence — list fields must stay lists.
    """
    model_config = ConfigDict(extra="ignore")

    company_name: Optional[str] = None
    vetting_verdict: Optional[str] = None
    salary_benchmark: Optional[str] = None
    detected_tech_stack: list[str] = Field(default_factory=list)
    engineering_culture: Optional[str] = None
    glassdoor_sentiment: Optional[str] = None
    recent_news_and_events: list[str] = Field(default_factory=list)
    architectural_trade_offs: Optional[str] = None
    red_flags: list[str] = Field(default_factory=list)
    green_flags: list[str] = Field(default_factory=list)
    reverse_interview_questions: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    confidence: Optional[int] = None

    @field_validator("detected_tech_stack", mode="before")
    @classmethod
    def _tech(cls, v):
        if isinstance(v, str) and v.strip() and not v.strip().startswith("["):
            parts = [p.strip() for p in v.split(",") if p.strip()]
            return parts or _parse_text_list(v)
        return _parse_text_list(v)

    @field_validator(
        "recent_news_and_events", "red_flags", "green_flags",
        "reverse_interview_questions", "source_urls", mode="before"
    )
    @classmethod
    def _coerce(cls, v):
        return _parse_text_list(v)


class CompanyDossierOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    company_name: str
    industry: Optional[str] = None
    company_type: Optional[str] = None
    is_legitimate_employer: Optional[bool] = None
    stability_outlook: Optional[str] = None
    vetting_verdict: Optional[str] = None
    confidence: Optional[int] = None
    dossier: DossierPayload = Field(default_factory=DossierPayload)
    source_urls: list[str] = Field(default_factory=list)
    markdown_path: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    job_count: int = 0
    linked_jobs: list[JobOut] = Field(default_factory=list)

    @field_validator("source_urls", mode="before")
    @classmethod
    def _urls(cls, v):
        return _parse_json_list(v)

    @field_validator("is_legitimate_employer", mode="before")
    @classmethod
    def _bool(cls, v):
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v == 1
        if isinstance(v, str):
            return v.strip() in ("1", "true", "True", "TRUE")
        return bool(v)


class JobListResponse(BaseModel):
    items: list[JobOut]
    total: int
    page: int
    page_size: int


class FunnelStats(BaseModel):
    found: int
    score_ge_80: int
    vetted_proceed: int
    cv_generated: int
    application_ready: int


class CandidateProfile(BaseModel):
    """A selectable candidate. Forward-compatible with config/profiles/."""
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    profile_path: str
    target_roles: list[str] = Field(default_factory=list)
    is_default: bool = False


class AgentRunRequest(BaseModel):
    """Body for POST /api/agents/{agent}/run."""
    candidate_id: Optional[str] = None
    min_score: Optional[int] = None
    query: Optional[str] = None            # Agent 1 only
    job_url: Optional[str] = Field(
        default=None,
        description="Agent 1 pasted job posting URL. # Ref: user-supplied listing ingest",
    )
    company: Optional[str] = None          # Agents 2/3/4
    job_id: Optional[int] = None           # Agents 2/3/4
    force_refresh: bool = False             # Dana / Leo / Clara per-job re-run
    force: bool = False                    # Dana: skip score gate (manual override)
    template: Optional[str] = None          # Agent 3 Canvas layout id
    document: Optional[str] = None          # Agent 3: cv | cover_letter (one file)


class AgentStatus(BaseModel):
    agent: str
    character: str
    state: AgentState = "IDLE"
    pid: Optional[int] = None
    started_at: Optional[str] = None
    message: Optional[str] = None
    last_lines: list[str] = Field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class AgentStatusMap(BaseModel):
    milo: AgentStatus
    rex: AgentStatus
    dana: AgentStatus
    leo: AgentStatus
    clara: AgentStatus


class HealthOut(BaseModel):
    status: str
    db_path: str
    job_count: int
    dossier_count: int


class TelegramBotOut(BaseModel):
    """Public Telegram bot identity for the dashboard 'open bot' link.

    Never includes the bot token. Username is what users search in Telegram.
    # Ref: Telegram Bot API getMe — username + numeric id
    """
    configured: bool
    username: Optional[str] = None
    bot_id: Optional[int] = None
    first_name: Optional[str] = None
    tme_url: Optional[str] = None
    tg_url: Optional[str] = None


# ---------------------------------------------------------------------------
# Profile editor models — strict typing, no Any. extra="allow" round-trips
# any keys the editor doesn't manage so the agents still parse the file.
# # Ref: config/master_profile.json schema
# ---------------------------------------------------------------------------

class ProfileBasics(BaseModel):
    """Identity and contact used on Leo CV / cover letter headers.

    # Ref: profile basics — email/phone plus optional address and profile URLs
    """
    model_config = ConfigDict(extra="allow")
    name: str
    location: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    website: Optional[str] = None
    github: Optional[str] = None
    linkedin: Optional[str] = None
    target_roles: list[str] = Field(default_factory=list)
    min_expected_salary_hkd: Optional[int] = None
    languages: list[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    institution: str
    degree: Optional[str] = None
    year: Optional[str] = None  # range string e.g. "2020 - 2024"


class ExperienceRole(BaseModel):
    """One title at an employer. Promotions are extra rows, not a new company.

    # Ref: same-company title change — own period / highlights / skills
    """
    model_config = ConfigDict(extra="allow")
    role: Optional[str] = None
    period: Optional[str] = None
    highlights: list[str] = Field(default_factory=list)
    skills_used: list[str] = Field(default_factory=list)


class ExperienceItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    company: str
    roles: list[ExperienceRole] = Field(default_factory=list)
    role: Optional[str] = None
    period: Optional[str] = None
    highlights: list[str] = Field(default_factory=list)
    skills_used: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def fold_legacy_and_sync_latest(self) -> "ExperienceItem":
        if not self.roles and (self.role or self.period or self.highlights or self.skills_used):
            self.roles = [
                ExperienceRole(
                    role=self.role,
                    period=self.period,
                    highlights=list(self.highlights),
                    skills_used=list(self.skills_used),
                )
            ]
        if self.roles:
            latest = self.roles[0]
            self.role = latest.role
            self.period = latest.period
            self.highlights = list(latest.highlights)
            self.skills_used = list(latest.skills_used)
        return self


class ProjectItem(BaseModel):
    """A shipped system: employment delivery or personal/side work.

    # Ref: profile projects — role + is_side_project for Leo CV labels
    """
    model_config = ConfigDict(extra="allow")
    name: str
    role: Optional[str] = None
    is_side_project: bool = False
    period: Optional[str] = None
    employer: Optional[str] = None
    description: Optional[str] = None
    tech_stack: list[str] = Field(default_factory=list)


class CertificationItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    issuer: Optional[str] = None
    year: Optional[int] = None
    category: Optional[str] = None


class LanguageItem(BaseModel):
    """Spoken/written language with CEFR-style or native/fluent label.

    # Ref: HK CV Languages section — not programming languages
    """
    model_config = ConfigDict(extra="allow")
    name: str
    proficiency: Optional[str] = None


class AwardItem(BaseModel):
    """Scholarship, competition, or professional award.

    # Ref: HK CV Awards / Honours — separate from certifications
    """
    model_config = ConfigDict(extra="allow")
    name: str
    issuer: Optional[str] = None
    year: Optional[int] = None
    description: Optional[str] = None


class Profile(BaseModel):
    """Full candidate profile written to config/master_profile.json or config/profiles/{id}.json."""
    model_config = ConfigDict(extra="allow")
    basics: ProfileBasics
    education: list[EducationItem] = Field(default_factory=list)
    technical_skills: dict[str, list[str]] = Field(default_factory=dict)
    experience: list[ExperienceItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    certifications: list[CertificationItem] = Field(default_factory=list)
    languages: list[LanguageItem] = Field(default_factory=list)
    awards: list[AwardItem] = Field(default_factory=list)
    acceptance_context: Optional[dict] = None  # PAC from Milo (free-form dict, round-trips)
    milo_readme_path: Optional[str] = None

    @model_validator(mode="after")
    def sync_language_labels(self) -> "Profile":
        """Keep basics.languages as display strings for Leo / Typst.

        # Ref: templates/resume.typ.j2 Languages section
        """
        if self.languages:
            labels: list[str] = []
            for item in self.languages:
                name = (item.name or "").strip()
                if not name:
                    continue
                level = (item.proficiency or "").strip()
                labels.append(f"{name} ({level})" if level else name)
            self.basics.languages = labels
        return self


class CreateProfileRequest(BaseModel):
    """Body for POST /api/candidates — create a new person."""
    id: str  # filename stem, validated server-side against [A-Za-z0-9_-]+
    name: str
    location: Optional[str] = "Hong Kong"
    linkedin: Optional[str] = None  # stored handle only; fetch is a separate button


class LinkedInImportRequest(BaseModel):
    """Body for POST /api/candidates/import-linkedin.

    # Ref: public /in/{slug} only — user-supplied username or URL
    """
    username: str
    candidate_id: Optional[str] = None


class JobStatusUpdate(BaseModel):
    """Body for PATCH /api/jobs/{id}/status — expire and/or unconsiderable."""

    expired: Optional[bool] = None
    unconsiderable: Optional[bool] = None

    @model_validator(mode="after")
    def _at_least_one_flag(self) -> "JobStatusUpdate":
        if self.expired is None and self.unconsiderable is None:
            raise ValueError("Provide expired and/or unconsiderable")
        return self


class JobShelfResponse(BaseModel):
    """Jobs hidden from the main kanban: low score, expired, unconsiderable."""

    low_score: list[JobOut] = Field(default_factory=list)
    expired: list[JobOut] = Field(default_factory=list)
    unconsiderable: list[JobOut] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class JobCheckResult(BaseModel):
    """Result of POST /api/jobs/{id}/check — did the source URL still resolve?"""
    exists: bool
    status_code: Optional[int] = None
    reason: str = ""
    final_url: Optional[str] = None
    expired_suggested: bool = False
    listing_mismatch: bool = False
    title_found: Optional[bool] = None


JobOut.model_rebuild()


