"""Talent Scout Agent v2 — privacy-safe Technical Career Path Architect."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from listing_filters import (  # noqa: E402
    is_junk_job_title,
    listing_text_supports_title,
    listing_url_problem,
)
from talent_scout_agent import (  # noqa: E402
    DEFAULT_PROFILE_PATH,
    DEEPSEEK_BASE_URL,
    EMBEDDING_DIM,
    HK_TZ,
    PIVOT_TRANSFERABILITY_FLOOR,
    PROJECT_ROOT,
    TalentScoutAgent as BaseTalentScoutAgent,
    compute_composite_match_score,
    extract_host,
    is_academic_non_job_url,
    is_academic_programme_title,
    is_job_posting_url,
    is_usable_company_name,
    lexical_embedding,
    now_hk_iso,
    parse_json_payload,
    passes_dual_score_gate,
    prefer_listing_title,
    resolve_employer_name,
    summarize_jd,
)

from activity_logger import log_activity  # noqa: E402
from llm_usage import finalize_usage  # noqa: E402
from milo_context import load_milo_readme, redact_pii_for_search  # noqa: E402
from notify import notify_job_update  # noqa: E402

# Ref: career-architect search tracks — diversified paid-employment lanes
MIN_SEARCH_TRACKS = 5
MAX_SEARCH_TRACKS = 7
DEFAULT_MIN_SCORE = 75
JOB_SEARCH_CONSTRAINTS = "vacancy hiring -PhD -MPhil"

PII_BASIC_KEYS = {
    "name",
    "email",
    "phone",
    "mobile",
    "address",
    "linkedin",
    "github",
    "website",
    "hkid",
    "passport",
}
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"\+?\d[\d\-\s()]{7,}\d")

# Deterministic ConTech / SSSS → universal capability language.
# Ref: de-verticalize vertical domain experience
VERTICAL_CAPABILITY_MAP: Sequence[tuple[str, str]] = (
    (
        r"(?i)\bSSSS\b|Smart Site Safety(?: System)?|4S\b|智慧工地(?:安全)?",
        "edge telemetry, high-throughput time-series data pipelines, "
        "distributed sensor networks, and local AI agent deployment",
    ),
    (
        r"(?i)construction telemetry|工地遙測|棚架|structural monitoring|結構監測",
        "asset and structural monitoring telemetry, high-ingestion time-series "
        "pipelines, and edge anomaly alerting",
    ),
    (
        r"(?i)\bConTech\b|建築科技",
        "cyber-physical systems, OT/IT integration, and field-device data platforms",
    ),
    (
        r"(?i)MCP Server",
        "structured tool-calling APIs and agent-to-system orchestration",
    ),
    (
        r"(?i)\bLiteRT\b",
        "on-device / edge ML runtime inference",
    ),
)

CORE_COMPETENCY_SEEDS: Sequence[str] = (
    "Full-Stack Python/FastAPI/PostgreSQL",
    "IoT telemetry and high-throughput time-series data pipelines",
    "edge AI model deployment",
    "distributed reliability and OT/IT integration",
)

INDUSTRY_ALIASES: Dict[str, str] = {
    "contech": "ConTech",
    "proptech": "PropTech",
    "smart facilities": "PropTech",
    "critical utilities": "Critical Utilities",
    "utilities": "Critical Utilities",
    "transport": "Critical Utilities",
    "logistics": "Logistics",
    "robotics": "Logistics",
    "fintech": "FinTech",
    "software": "Software",
    "information technology": "Software",
    "it services": "Software",
    "ai": "AI / Automation",
    "artificial intelligence": "AI / Automation",
}

JOB_FIT_JSON_EXAMPLE: Dict[str, object] = {
    "is_valid_job": True,
    "is_direct_hire": True,
    "is_hong_kong_role": True,
    "company_name": "Example Ltd",
    "job_title": "Platform Engineer",
    "target_industry": "PropTech",
    "location_mode": "Hybrid",
    "salary_range": "Not Disclosed",
    "tech_stack_required": ["Python", "PostgreSQL"],
    "hard_skill_match_score": 70,
    "transferability_score": 88,
    "composite_match_score": 78,
    "transferable_strengths": ["Time-series ingestion maps to BMS telemetry"],
    "bridging_gaps": ["Building protocol names (BACnet)"],
    "career_advisory_note": "Why this pivot compounds the candidate's platform skills.",
    "recommendation_reason": "Short hiring recommendation.",
}

HORIZON_JSON_EXAMPLE: Dict[str, object] = {
    "abstract_competencies": ["Python/FastAPI platforms", "time-series telemetry"],
    "transferable_themes": ["high-reliability event pipelines"],
    "search_tracks": [
        {
            "track_id": "proptech",
            "industry": "PropTech",
            "rationale": "Smart-facilities platforms reuse sensor telemetry.",
            "search_query": "smart building IoT platform engineer Python FastAPI Hong Kong",
            "target_domain_hints": ["BMS", "smart facilities", "digital twin"],
            "target_companies": ["Swire"],
        }
    ],
}


class AnonymizedProfile(BaseModel):
    """Privacy-safe profile sent to search/LLM. No person or employer identifiers.

    # Ref: PII redaction & abstract profile loader
    """

    location_region: str = "Hong Kong"
    target_roles: List[str] = Field(default_factory=list)
    years_of_experience: Optional[int] = None
    skills: List[str] = Field(default_factory=list)
    abstract_capabilities: List[str] = Field(default_factory=list)
    domain_agnostic_highlights: List[str] = Field(default_factory=list)
    preferred_mode: str = "Hybrid or Remote"
    min_expected_salary_hkd: Optional[int] = None


class CareerSearchTrack(BaseModel):
    """One Tavily query track produced before search.

    # Ref: pre-search horizon expansion
    """

    track_id: str
    industry: str
    rationale: str
    search_query: str
    target_domain_hints: List[str] = Field(default_factory=list)
    target_companies: List[str] = Field(default_factory=list)

    @field_validator("industry")
    @classmethod
    def normalize_industry(cls, value: str) -> str:
        return normalize_target_industry(value)


class CareerHorizonPlan(BaseModel):
    """Cross-domain search plan grounded in abstract competencies.

    # Ref: Technical Career Path Architect
    """

    abstract_competencies: List[str] = Field(default_factory=list)
    transferable_themes: List[str] = Field(default_factory=list)
    search_tracks: List[CareerSearchTrack] = Field(default_factory=list)


class JobFitEvaluation(BaseModel):
    """Dual-score job evaluation with explicit cross-domain reasoning.

    # Ref: career-architect evaluation matrix
    """

    is_valid_job: bool = Field(description="真實合法 IT 職缺（非詐騙、非純廣告、非過期）")
    is_direct_hire: bool = Field(description="企業官方直聘；False 表示獵頭代招")
    is_hong_kong_role: bool = Field(description="工作地為香港（含需在港的 Hybrid）")
    company_name: str = Field(
        description="僱主法定或常用名稱；未知則空字串，禁止 Not Disclosed"
    )
    job_title: str
    target_industry: str = Field(
        description="ConTech / PropTech / Critical Utilities / Logistics / FinTech"
    )
    location_mode: str = Field(description="On-site / Hybrid / Remote")
    salary_range: Optional[str] = Field(default=None, description="薪資或 Not Disclosed")
    tech_stack_required: List[str] = Field(description="JD 要求的核心技術棧")
    hard_skill_match_score: int = Field(
        ge=0, le=100, description="語言/框架直接重疊 0-100"
    )
    transferability_score: int = Field(
        ge=0, le=100, description="架構重疊與領域可遷移性 0-100"
    )
    composite_match_score: int = Field(
        default=0, ge=0, le=100, description="加權綜合分；由純函數覆寫"
    )
    transferable_strengths: List[str] = Field(
        description="為何分散式/IoT/AI 經驗能解此職缺痛點"
    )
    bridging_gaps: List[str] = Field(description="需補的少量領域知識")
    career_advisory_note: str = Field(description="職涯建築師對此 pivot 的策略建議")
    recommendation_reason: str = Field(description="推薦或淘汰的關鍵依據")

    @field_validator("target_industry")
    @classmethod
    def normalize_industry(cls, value: str) -> str:
        return normalize_target_industry(value)

    @model_validator(mode="after")
    def apply_deterministic_composite(self) -> "JobFitEvaluation":
        self.composite_match_score = compute_composite_match_score(
            self.hard_skill_match_score,
            self.transferability_score,
        )
        return self


def normalize_target_industry(value: str) -> str:
    """Map free-text industry labels onto the hiring taxonomy.

    # Ref: target_industry vocabulary
    """
    key = " ".join((value or "").strip().lower().split())
    if not key:
        return "Other"
    return INDUSTRY_ALIASES.get(key, value.strip())


def redact_pii_text(text: str, secrets: Sequence[str]) -> str:
    """Strip emails, phones, and known person/employer/school strings.

    # Ref: PII redaction
    """
    cleaned = EMAIL_RE.sub("[REDACTED_EMAIL]", text or "")
    cleaned = PHONE_RE.sub("[REDACTED_PHONE]", cleaned)
    ordered = sorted({item.strip() for item in secrets if item and item.strip()}, key=len, reverse=True)
    for secret in ordered:
        if len(secret) < 3:
            continue
        cleaned = re.sub(re.escape(secret), "[REDACTED]", cleaned, flags=re.I)
    return " ".join(cleaned.split())


def deverticalize_text(text: str) -> str:
    """Rewrite vertical product jargon into universal engineering capabilities.

    # Ref: de-verticalize SSSS / ConTech experience
    """
    matched: List[str] = []
    rewritten = text
    for pattern, capability in VERTICAL_CAPABILITY_MAP:
        if re.search(pattern, rewritten):
            if capability not in matched:
                matched.append(capability)
            rewritten = re.sub(pattern, " ", rewritten)
    combined = " ".join(matched + [rewritten]).strip() if matched else rewritten
    return " ".join(combined.split())


def _collect_pii_secrets(raw: dict) -> List[str]:
    secrets: List[str] = []
    basics = raw.get("basics") if isinstance(raw.get("basics"), dict) else {}
    for key in PII_BASIC_KEYS:
        value = basics.get(key)
        if isinstance(value, str) and value.strip():
            secrets.append(value.strip())
    for school in raw.get("education") or []:
        if isinstance(school, dict):
            institution = school.get("institution")
            if isinstance(institution, str) and institution.strip():
                secrets.append(institution.strip())
    for job in raw.get("experience") or []:
        if isinstance(job, dict):
            company = job.get("company")
            if isinstance(company, str) and company.strip():
                secrets.append(company.strip())
    return secrets


def _estimate_years_of_experience(experience: Sequence[object]) -> Optional[int]:
    years: List[int] = []
    for job in experience:
        if not isinstance(job, dict):
            continue
        period = str(job.get("period") or "")
        found = [int(item) for item in re.findall(r"(?:19|20)\d{2}", period)]
        years.extend(found)
        if re.search(r"(?i)present|now|至今|現職", period) and found:
            years.append(datetime_now_year())
    if not years:
        return None
    span = max(years) - min(years)
    return max(1, min(40, span if span > 0 else 1))


def datetime_now_year() -> int:
    """Current calendar year in Asia/Hong_Kong.

    # Ref: timezone standard — Asia/Hong_Kong (UTC+8)
    """
    from datetime import datetime

    return datetime.now(HK_TZ).year


def anonymize_profile_dict(raw: dict) -> AnonymizedProfile:
    """Build an abstract profile from master_profile.json-shaped data."""
    secrets = _collect_pii_secrets(raw)
    basics = raw.get("basics") if isinstance(raw.get("basics"), dict) else {}
    skills: List[str] = []
    highlights: List[str] = []
    for job in raw.get("experience") or []:
        if not isinstance(job, dict):
            continue
        skills.extend(item for item in (job.get("skills_used") or []) if isinstance(item, str))
        for line in job.get("highlights") or []:
            if isinstance(line, str) and line.strip():
                highlights.append(deverticalize_text(redact_pii_text(line, secrets)))
    for project in raw.get("projects") or []:
        if not isinstance(project, dict):
            continue
        skills.extend(item for item in (project.get("tech_stack") or []) if isinstance(item, str))
        description = project.get("description")
        if isinstance(description, str) and description.strip():
            highlights.append(deverticalize_text(redact_pii_text(description, secrets)))
    unique_skills = list(dict.fromkeys(skills))
    capabilities = list(CORE_COMPETENCY_SEEDS)
    for skill in unique_skills:
        token = skill.strip()
        if token and token not in capabilities:
            capabilities.append(token)
    target_roles = basics.get("target_roles") if isinstance(basics.get("target_roles"), list) else []
    roles = [str(item) for item in target_roles if str(item).strip()]
    salary = basics.get("min_expected_salary_hkd")
    salary_int = salary if isinstance(salary, int) else None
    location = basics.get("location")
    region = "Hong Kong"
    if isinstance(location, str) and "hong kong" in location.lower():
        region = "Hong Kong"
    return AnonymizedProfile(
        location_region=region,
        target_roles=roles,
        years_of_experience=_estimate_years_of_experience(raw.get("experience") or []),
        skills=unique_skills,
        abstract_capabilities=capabilities,
        domain_agnostic_highlights=highlights,
        preferred_mode="Hybrid or Remote",
        min_expected_salary_hkd=salary_int,
    )


def load_anonymized_profile(profile_path: Path | str = DEFAULT_PROFILE_PATH) -> dict:
    """Read config/master_profile.json, strip PII, and de-verticalize experience.

    # Ref: PII redaction & abstract profile loader
    """
    path = Path(profile_path)
    if not path.is_file():
        return AnonymizedProfile(
            skills=["Python", "FastAPI", "PostgreSQL"],
            abstract_capabilities=list(CORE_COMPETENCY_SEEDS),
        ).model_dump()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("master_profile.json must be a JSON object")
    return anonymize_profile_dict(raw).model_dump()


def fallback_horizon_plan(abstract_profile: dict) -> CareerHorizonPlan:
    """Deterministic HK paid-job tracks when the planning LLM call fails.

    Queries stay short and role-diverse so Tavily is not pinned to ConTech jargon.

    # Ref: pre-search horizon expansion fallback
    """
    roles = abstract_profile.get("target_roles") or []
    role_hint = " ".join(str(r) for r in roles[:2]) if isinstance(roles, list) else ""
    tracks = [
        CareerSearchTrack(
            track_id="software",
            industry="Software",
            rationale="Core paid software-engineering vacancies across HK product and IT-services firms.",
            search_query="software engineer OR backend engineer Python Hong Kong",
            target_domain_hints=["backend", "API", "microservices"],
            target_companies=[],
        ),
        CareerSearchTrack(
            track_id="fullstack",
            industry="Software",
            rationale="Full-stack web roles using Python/React, not campus research programmes.",
            search_query="full stack developer OR fullstack engineer React Python Hong Kong",
            target_domain_hints=["React", "FastAPI", "web platform"],
            target_companies=[],
        ),
        CareerSearchTrack(
            track_id="ai_automation",
            industry="AI / Automation",
            rationale="LLM, agent, and workflow-automation engineering jobs in industry.",
            search_query="AI engineer OR LLM OR LangGraph OR n8n automation engineer Hong Kong",
            target_domain_hints=["LLM", "agents", "workflow automation"],
            target_companies=[],
        ),
        CareerSearchTrack(
            track_id="iot_platform",
            industry="ConTech",
            rationale="Industrial IoT / telemetry platform jobs (employment, not university RPG).",
            search_query="IoT platform engineer OR telemetry OR time-series backend Hong Kong",
            target_domain_hints=["IoT", "MQTT", "time-series"],
            target_companies=[],
        ),
        CareerSearchTrack(
            track_id="proptech",
            industry="PropTech",
            rationale="Smart-building and PropTech product engineering vacancies.",
            search_query="PropTech OR smart building software engineer Hong Kong",
            target_domain_hints=["BMS", "smart facilities"],
            target_companies=["Swire"],
        ),
        CareerSearchTrack(
            track_id="fintech",
            industry="FinTech",
            rationale="Banking/FinTech backend and platform roles broaden away from a single vertical.",
            search_query="Python backend OR platform engineer bank OR fintech Hong Kong",
            target_domain_hints=["payments", "observability"],
            target_companies=["HSBC", "HKEX"],
        ),
        CareerSearchTrack(
            track_id="utilities",
            industry="Critical Utilities",
            rationale="MTR/CLP-class software and OT/IT engineering vacancies.",
            search_query="software engineer railway OR utility OR SCADA Hong Kong",
            target_domain_hints=["OT/IT", "condition monitoring"],
            target_companies=["MTR", "CLP"],
        ),
    ]
    if role_hint:
        tracks.insert(
            0,
            CareerSearchTrack(
                track_id="profile_roles",
                industry="Software",
                rationale="Direct search for the candidate's stated target roles.",
                search_query=f"{role_hint} Hong Kong",
                target_domain_hints=[],
                target_companies=[],
            ),
        )
    return CareerHorizonPlan(
        abstract_competencies=list(abstract_profile.get("abstract_capabilities") or CORE_COMPETENCY_SEEDS),
        transferable_themes=[
            "backend and full-stack product engineering",
            "AI / workflow automation",
            "IoT and high-reliability platforms",
        ],
        search_tracks=tracks[:MAX_SEARCH_TRACKS],
    )


def loads_llm_json_object(raw: str) -> dict:
    """Parse DeepSeek JSON mode output, repairing common syntax errors."""
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


def coerce_job_fit_payload(raw: str) -> dict:
    """Fill aliases so a missing dual-score field does not drop the JD."""
    payload = loads_llm_json_object(raw)
    if "hard_skill_match_score" not in payload and "match_score" in payload:
        payload["hard_skill_match_score"] = payload["match_score"]
    payload.setdefault("is_valid_job", False)
    payload.setdefault("is_direct_hire", False)
    payload.setdefault("is_hong_kong_role", False)
    payload.setdefault("company_name", "")
    payload.setdefault("job_title", "")
    payload.setdefault("target_industry", "Other")
    payload.setdefault("location_mode", "On-site")
    payload.setdefault("tech_stack_required", [])
    payload.setdefault("hard_skill_match_score", 0)
    payload.setdefault("transferability_score", 0)
    payload.setdefault("transferable_strengths", payload.get("matched_skills") or [])
    payload.setdefault("bridging_gaps", payload.get("missing_skills") or [])
    payload.setdefault("career_advisory_note", "")
    payload.setdefault("recommendation_reason", "")
    for key in ("tech_stack_required", "transferable_strengths", "bridging_gaps"):
        value = payload.get(key)
        if isinstance(value, str):
            payload[key] = [value] if value.strip() else []
    return payload


def fit_embedding_dim(vector: Sequence[float], dim: int) -> List[float]:
    """Pad or trim vectors so sqlite-vec width stays stable.

    # Ref: sqlite-vec embedding dim compatibility (1536d / 384d)
    """
    values = [float(item) for item in vector]
    if len(values) == dim:
        return values
    if len(values) > dim:
        values = values[:dim]
    else:
        values = values + [0.0] * (dim - len(values))
    norm = sum(item * item for item in values) ** 0.5 or 1.0
    return [item / norm for item in values]


def fastembed_vector(text: str) -> Optional[List[float]]:
    """Optional FastEmbed backend; None if the extra is not installed."""
    try:
        from fastembed import TextEmbedding
    except ImportError:
        return None
    model_name = os.environ.get("FASTEMBED_MODEL", "BAAI/bge-small-en-v1.5")
    model = TextEmbedding(model_name=model_name)
    raw = next(model.embed([text]))
    return [float(item) for item in raw]


def compose_track_query(track: CareerSearchTrack) -> str:
    hints = " ".join(track.target_domain_hints[:4])
    core = " ".join(part for part in (track.search_query, hints) if part).strip()
    return f"{core} {JOB_SEARCH_CONSTRAINTS}".strip()


class TalentScoutAgent(BaseTalentScoutAgent):
    """Hong Kong scout that expands career horizons before Tavily search."""

    def get_embedding(self, text: str) -> List[float]:
        backend = (os.environ.get("EMBEDDING_BACKEND") or "lexical").strip().lower()
        if backend == "fastembed":
            vector = fastembed_vector(text)
            if vector:
                return fit_embedding_dim(vector, EMBEDDING_DIM)
        return lexical_embedding(text, EMBEDDING_DIM)

    def expand_career_horizons(self, abstract_profile: dict) -> CareerHorizonPlan:
        """Ask DeepSeek how core competencies transfer across HK industries.

        Runs before any Tavily call. Output is search tracks, not job URLs.
        # Ref: pre-search cross-domain career reasoning
        """
        fallback = fallback_horizon_plan(abstract_profile)
        example = json.dumps(HORIZON_JSON_EXAMPLE, ensure_ascii=False)
        system_prompt = f"""
You are a Technical Career Path Architect for the Hong Kong **paid employment** market.
The profile is anonymized: no names, emails, phones, employers, or schools.

Search ONLY for real job vacancies (JobsDB / CTgoodjobs / LinkedIn jobs / ATS / careers pages).
Do NOT plan queries for university research postgraduate programmes, PhD/MPhil, admissions,
taught degrees, studentships, or academic prospectuses.

Diversify both industries AND role titles. Include at least:
- software / backend / full-stack engineer
- AI / LLM / automation engineer
- plus 2-3 adjacent domains (PropTech, utilities, FinTech, IoT platform, data)

Keep each search_query SHORT (under 16 words). Do not dump the whole skill list into every query.
Each query should include a role noun (engineer, developer, architect) plus Hong Kong.

Return JSON only. Generate {MIN_SEARCH_TRACKS}-{MAX_SEARCH_TRACKS} distinct search_tracks.
Do not include person names, emails, or current/past employer names.
target_companies may be well-known HK organisations in that industry.

Example:
{example}
"""
        user_prompt = json.dumps(abstract_profile, ensure_ascii=False)
        try:
            response = self.client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )
            raw = response.choices[0].message.content or ""
            plan = CareerHorizonPlan.model_validate(loads_llm_json_object(raw))
        except Exception as exc:
            print(f"⚠️ [Horizon plan fallback] {exc}")
            log_activity("Rex", "Horizon expansion failed, using fallback", level="WARN")
            return fallback
        if len(plan.search_tracks) < MIN_SEARCH_TRACKS:
            seen = {track.track_id for track in plan.search_tracks}
            for extra in fallback.search_tracks:
                if extra.track_id in seen:
                    continue
                plan.search_tracks.append(extra)
                if len(plan.search_tracks) >= MIN_SEARCH_TRACKS:
                    break
        plan.search_tracks = plan.search_tracks[:MAX_SEARCH_TRACKS]
        if not plan.abstract_competencies:
            plan.abstract_competencies = fallback.abstract_competencies
        return plan

    def evaluate_job(
        self,
        jd_text: str,
        user_profile: dict,
        search_track: Optional[CareerSearchTrack] = None,
        listing_title: str = "",
        listing_url: str = "",
    ) -> Optional[JobFitEvaluation]:
        """Dual-score authenticity + hard-skill + transferability evaluation.

        # Ref: DeepSeek API response_format json_object
        """
        example = json.dumps(JOB_FIT_JSON_EXAMPLE, ensure_ascii=False)
        track_blob = ""
        if search_track:
            track_blob = (
                f"Search track industry: {search_track.industry}\n"
                f"Track rationale: {search_track.rationale}\n"
            )
        system_prompt = f"""
You are a Technical Career Path Architect and Hong Kong IT hiring analyst.
Compare the anonymized candidate profile with the job description.

Rules:
1. is_valid_job is TRUE only for a paid employment vacancy. FALSE for research postgraduate
   programmes, PhD/MPhil, admissions, studentships, internships-only academic posts, or ads.
2. is_hong_kong_role / is_direct_hire must be factual from the JD.
3. company_name is the real employer or empty string. Never write Not Disclosed.
4. job_title MUST be the posting's actual title copied from the JD heading or the provided
   board title. Do NOT paraphrase into a nicer generic title (e.g. do not turn
   "Building Services Engineer" into "Platform Engineer").
5. hard_skill_match_score = direct language/framework overlap (0-100).
6. transferability_score = architectural overlap and domain translatability (0-100).
   High transfer means IoT/time-series/edge-AI/distributed reliability clearly solves this role's pain.
7. composite_match_score will be recomputed; still include it.
8. transferable_strengths: concrete arguments, not generic praise.
9. bridging_gaps: minor domain knowledge to ramp, not deal-breakers.
10. BILINGUAL OUTPUT: Write all text fields (recommendation_reason, transferable_strengths, bridging_gaps, career_advisory_note) in BOTH English and Traditional Chinese. Format: "English sentence. 繁體中文句子。" Each list item should also be bilingual.
11. career_advisory_note: why this pivot is strategically valuable.
12. JSON only, keys exactly: {list(JOB_FIT_JSON_EXAMPLE.keys())}.
   Escape inner quotes. Keep strings under 280 characters.

Example:
{example}

Anonymized profile:
{json.dumps(user_profile, ensure_ascii=False)}
{track_blob}
"""
        try:
            response = self.client.chat.completions.create(
                model=self.chat_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": (
                        f"Board title: {listing_title or '(unknown)'}\n"
                        f"URL: {listing_url or '(unknown)'}\n"
                        f"職位描述 (JD):\n{jd_text}"
                    )},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
        except Exception as exc:
            print(f"⚠️ [DeepSeek evaluate failed] {exc}")
            log_activity("Rex", f"JD evaluate failed: {exc}", level="WARN")
            return None
        raw = response.choices[0].message.content
        if not raw:
            return None
        try:
            return JobFitEvaluation.model_validate(coerce_job_fit_payload(raw))
        except Exception as exc:
            print(f"⚠️ [JSON parse skipped] {exc}")
            return None

    def run_pipeline(
        self,
        search_keywords: str = "",
        user_profile: Optional[dict] = None,
        min_score: int = DEFAULT_MIN_SCORE,
        target_companies: Optional[Sequence[str]] = None,
        extra_domains: Optional[Sequence[str]] = None,
        profile_path: Path = DEFAULT_PROFILE_PATH,
    ) -> int:
        """Anonymize → expand horizons → Tavily lanes → dual-score → embed → store.

        Accepts composite_match_score >= min_score OR transferability_score >= 85.
        # Ref: dual-score gate
        """
        from milo_intake import MiloIntakeAgent
        milo = MiloIntakeAgent(profile_path=profile_path)
        milo.sync_compress_if_new_chat(source="rex")
        if milo.profile:
            if not user_profile:
                user_profile = milo.profile
            elif milo.profile.get("acceptance_context"):
                user_profile.setdefault("acceptance_context", milo.profile["acceptance_context"])

        if user_profile and "basics" in user_profile:
            abstract = anonymize_profile_dict(user_profile).model_dump()
        elif user_profile:
            abstract = user_profile
        else:
            abstract = load_anonymized_profile(profile_path)

        log_activity("Rex", "Agent started: privacy-safe profile loaded, PII stripped")
        print("🧭 [Abstract profile] PII stripped; sending de-verticalized capabilities only.")
        for capability in abstract.get("abstract_capabilities") or []:
            print(f"   • {capability}")

        # --- Milo PAC soft guidance (broaden, NOT filter) ---
        # Ref: Milo design — PAC feeds into horizon expansion as seed context.
        pac = (user_profile or {}).get("acceptance_context") if user_profile else None
        if not pac and "acceptance_context" in abstract:
            pac = abstract.get("acceptance_context")
        if pac:
            narrative = pac.get("executive_narrative", "")
            skills = pac.get("core_transferable_skills", [])
            industries = pac.get("target_industries", [])
            archetypes = pac.get("role_archetypes", [])
            deal_breakers = pac.get("absolute_deal_breakers", [])
            if narrative:
                abstract["milo_narrative"] = narrative
                print(f"🎯 [PAC narrative] {narrative[:100]}...")
            if skills:
                abstract.setdefault("abstract_capabilities", []).extend(skills)
            if industries:
                abstract["pac_target_industries"] = industries
            if archetypes:
                abstract["pac_role_archetypes"] = archetypes
            abstract["pac_deal_breakers"] = deal_breakers
            log_activity("Rex", f"PAC loaded: {len(skills)} skills, {len(industries)} industries, "
                         f"{len(archetypes)} archetypes, {len(deal_breakers)} deal-breakers")
        else:
            abstract["pac_deal_breakers"] = []

        milo_readme = load_milo_readme(profile_path)
        if milo_readme:
            abstract["milo_context_readme"] = redact_pii_for_search(milo_readme)[:4000]
            log_activity("Rex", f"Milo README loaded ({len(milo_readme)} chars)")

        print("🔭 [Horizon expansion] DeepSeek planning before Tavily…")
        plan = self.expand_career_horizons(abstract)
        log_activity("Rex", f"Horizon expansion: planned {len(plan.search_tracks)} search tracks")
        if search_keywords.strip():
            plan.search_tracks = [
                CareerSearchTrack(
                    track_id="user_query",
                    industry="Other",
                    rationale="Caller-supplied keywords merged into the search plan.",
                    search_query=search_keywords.strip(),
                    target_domain_hints=[],
                    target_companies=list(target_companies or []),
                ),
                *plan.search_tracks,
            ][:MAX_SEARCH_TRACKS]

        discovered_count = 0
        seen_urls: set[str] = set()
        extra = list(extra_domains or [])

        for track in plan.search_tracks:
            query = compose_track_query(track)
            companies = list(dict.fromkeys([*(track.target_companies or []), *(target_companies or [])]))
            print(f"🛤️  [Track:{track.track_id}|{track.industry}] {query}")
            log_activity(
                "Rex",
                f"Searching track {track.track_id} ({track.industry}): {query}",
            )
            try:
                raw_jobs = self.search_verified_jobs(
                    query,
                    target_companies=companies or None,
                    extra_domains=extra or None,
                )
            except Exception as exc:
                print(f"⚠️ [Track search failed] {track.track_id}: {exc}")
                log_activity("Rex", f"Track {track.track_id} search failed: {exc}", level="ERROR")
                continue
            for raw in raw_jobs:
                url = raw.get("url")
                if not url or url in seen_urls or self.db_manager.job_exists(url):
                    continue
                if is_academic_non_job_url(url) or is_academic_programme_title(raw.get("title") or ""):
                    print(f"⏭️  [Not a paid job listing] {raw.get('title')} {url}")
                    continue
                url_issue = listing_url_problem(url)
                if url_issue or not is_job_posting_url(url):
                    print(f"⏭️  [Not a posting URL] {url_issue or url}")
                    continue
                if is_junk_job_title(raw.get("title") or ""):
                    print(f"⏭️  [Catalogue title] {raw.get('title')} {url}")
                    continue
                seen_urls.add(url)

                content = raw.get("raw_content") or raw.get("content") or ""
                try:
                    eval_res = self.evaluate_job(
                        content,
                        abstract,
                        search_track=track,
                        listing_title=raw.get("title") or "",
                        listing_url=url,
                    )
                except Exception as exc:
                    print(f"⚠️ [Evaluate skipped] {url}: {exc}")
                    log_activity("Rex", f"Evaluate skipped for {url}: {exc}", level="WARN")
                    continue
                if not eval_res or not eval_res.is_valid_job:
                    continue
                if is_academic_programme_title(eval_res.job_title):
                    print(f"⏭️  [LLM labelled an academic programme] {eval_res.job_title}")
                    continue
                if not eval_res.is_hong_kong_role:
                    continue
                # --- Milo absolute deal-breakers check (minimal hard filter) ---
                # Ref: Only absolute_deal_breakers act as hard filter. NOT a blacklist.
                deal_breakers = abstract.get("pac_deal_breakers", [])
                if deal_breakers:
                    from talent_scout_agent import passes_absolute_deal_breakers
                    passed, reason = passes_absolute_deal_breakers(content, deal_breakers)
                    if not passed:
                        print(f"⏭️  [Deal-breaker: {reason}] {eval_res.job_title}")
                        log_activity("Rex", f"Rejected by deal-breaker '{reason}': {eval_res.job_title}", level="WARN")
                        continue
                log_activity(
                    "Rex",
                    f"Evaluating JD: {eval_res.company_name} — {eval_res.job_title} "
                    f"(hard={eval_res.hard_skill_match_score} "
                    f"transfer={eval_res.transferability_score} "
                    f"composite={eval_res.composite_match_score})",
                )
                company_name = eval_res.company_name
                if not is_usable_company_name(company_name):
                    resolved = resolve_employer_name(url, content)
                    if resolved:
                        print(f"🏷️  [Employer recovered] {eval_res.job_title} → {resolved}")
                        company_name = resolved
                if not is_usable_company_name(company_name):
                    print(f"⏭️  [Skip anonymous employer] {eval_res.job_title}")
                    continue

                below_gate = not passes_dual_score_gate(
                    eval_res.composite_match_score,
                    eval_res.transferability_score,
                    min_score=min_score,
                )
                if below_gate:
                    print(
                        f"📦 [Store below dual-score gate] {eval_res.job_title} "
                        f"composite={eval_res.composite_match_score} "
                        f"transfer={eval_res.transferability_score}"
                    )
                    log_activity(
                        "Rex",
                        f"Stored below dual-score gate: {eval_res.job_title}",
                        level="WARN",
                    )

                stored_title = prefer_listing_title(
                    raw.get("title") or "", url, eval_res.job_title
                )
                if is_junk_job_title(stored_title):
                    print(f"⏭️  [Catalogue title after normalize] {stored_title}")
                    continue
                if not listing_text_supports_title(content, stored_title):
                    print(
                        f"⏭️  [Source snippet does not match title] {stored_title} {url}"
                    )
                    log_activity(
                        "Rex",
                        f"Skipped URL/title mismatch: {stored_title}",
                        level="WARN",
                    )
                    continue
                job_summary_text = (
                    f"{company_name} {stored_title} "
                    f"{' '.join(eval_res.tech_stack_required)} "
                    f"{eval_res.target_industry}"
                )
                try:
                    embedding = self.get_embedding(job_summary_text)
                    try:
                        snippet = summarize_jd(self.client, self.chat_model, content)
                    except Exception as exc:
                        print(f"⚠️ [JD summary failed] {stored_title}: {exc}")
                        snippet = (content or "")[:500]
                    job_record = {
                        "job_url": url,
                        "company_name": company_name,
                        "job_title": stored_title,
                        "source_domain": extract_host(url),
                        "source_lane": raw.get("source_lane", "unknown"),
                        "location_mode": eval_res.location_mode,
                        "salary_range": eval_res.salary_range,
                        "match_score": eval_res.composite_match_score,
                        "matched_skills": eval_res.transferable_strengths,
                        "missing_skills": eval_res.bridging_gaps,
                        "is_direct_hire": eval_res.is_direct_hire,
                        "recommendation_reason": eval_res.recommendation_reason,
                        "jd_snippet": snippet,
                        "created_at": now_hk_iso(),
                        "target_industry": eval_res.target_industry,
                        "hard_skill_match_score": eval_res.hard_skill_match_score,
                        "transferability_score": eval_res.transferability_score,
                        "transferable_strengths": eval_res.transferable_strengths,
                        "career_advisory_note": eval_res.career_advisory_note,
                    }
                    job_id = self.db_manager.save_job(job_record, embedding)
                except Exception as exc:
                    print(f"⚠️ [Store skipped] {stored_title}: {exc}")
                    log_activity("Rex", f"Store skipped: {exc}", level="ERROR")
                    continue
                discovered_count += 1
                notify_job_update(
                    "Rex",
                    "Job archived (below gate)" if below_gate else "New job stored",
                    company=company_name,
                    title=stored_title,
                    score=eval_res.composite_match_score,
                    url=url,
                    extra=(
                        f"hard={eval_res.hard_skill_match_score} "
                        f"transfer={eval_res.transferability_score} "
                        f"{eval_res.target_industry}"
                    ),
                )
                log_activity(
                    "Rex",
                    f"Stored job #{job_id}: {company_name} — {eval_res.job_title} "
                    f"[{eval_res.target_industry}]",
                )
                print(
                    f"🎯 [職涯路徑職缺] {company_name} - {eval_res.job_title} "
                    f"| {eval_res.target_industry} "
                    f"| hard={eval_res.hard_skill_match_score} "
                    f"transfer={eval_res.transferability_score} "
                    f"composite={eval_res.composite_match_score} "
                    f"| {job_record['source_lane']}"
                )
                if eval_res.career_advisory_note:
                    print(f"   💡 {eval_res.career_advisory_note}")

        print(
            f"\n✅ 職涯路徑掃描完成！新增 {discovered_count} 筆職缺至資料庫"
            f"（含分數門檻以下的真實職缺；Dana 只處理 composite>={min_score}）。"
        )
        log_activity("Rex", f"Pipeline complete: {discovered_count} jobs stored")
        notify_job_update(
            "Rex",
            "Scan finished",
            extra=f"{discovered_count} job(s) stored",
        )
        return discovered_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hong Kong Technical Career Path Architect")
    parser.add_argument("--query", default="", help="Optional extra search keywords (merged as one track)")
    parser.add_argument("--min-score", type=int, default=DEFAULT_MIN_SCORE)
    parser.add_argument(
        "--profile",
        default=str(DEFAULT_PROFILE_PATH),
        help="Path to master_profile.json (PII is stripped before LLM/Tavily)",
    )
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    from env_keys import deepseek_api_key, tavily_api_key
    tavily_key = tavily_api_key()
    deepseek_key = deepseek_api_key()
    if not tavily_key or not deepseek_key:
        raise SystemExit(
            "Set TAVILY_API_KEY and DEEPSEEK_API_KEY in the environment or a .env file."
        )

    agent = TalentScoutAgent(
        tavily_api_key=tavily_key,
        deepseek_api_key=deepseek_key,
    )
    print(f"Using DeepSeek {agent.chat_model} @ {DEEPSEEK_BASE_URL}")
    try:
        agent.run_pipeline(
            search_keywords=args.query,
            min_score=args.min_score,
            profile_path=Path(args.profile),
        )
    except Exception as exc:
        log_activity("Rex", f"Pipeline crashed: {exc}", level="ERROR")
        print(f"❌ Rex pipeline crashed: {exc}")
        finalize_usage("Rex")
        raise SystemExit(1) from exc
    finalize_usage("Rex")
    try:
        print("\n🔍 sqlite-vec smoke test:")
        query_vector = agent.get_embedding("High throughput IoT time-series platform backend")
        for match in agent.db_manager.search_similar_jobs(query_vector, limit=3):
            print(
                f" - [{match['company']}] {match['title']} | "
                f"composite: {match['match_score']} | distance: {match['distance']:.4f}"
            )
    except Exception as exc:
        print(f"⚠️ sqlite-vec smoke test skipped: {exc}")
        log_activity("Rex", f"sqlite-vec smoke test skipped: {exc}", level="WARN")
