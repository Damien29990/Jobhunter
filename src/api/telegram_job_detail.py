"""Plain-text job card for Telegram (Rex ingest + Clara follow-up).

# Ref: job_postings scores / matched_skills / missing_skills · Asia/Hong_Kong
"""

from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from application_followup import application_status_label


class JobTelegramDetail(BaseModel):
    """Fields shown on a Telegram job reply. # Ref: job_postings"""

    model_config = ConfigDict(extra="ignore")

    id: Optional[int] = None
    company_name: Optional[str] = None
    job_title: Optional[str] = None
    application_status: Optional[str] = None
    match_score: Optional[int] = None
    hard_skill_match_score: Optional[int] = None
    transferability_score: Optional[int] = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    location_mode: Optional[str] = None
    salary_range: Optional[str] = None
    job_url: Optional[str] = None
    recommendation_reason: Optional[str] = None
    career_advisory_note: Optional[str] = None
    application_note: Optional[str] = None
    employer_update_note: Optional[str] = None
    application_status_at: Optional[str] = None
    suitable: Optional[bool] = None

    @field_validator(
        "match_score",
        "hard_skill_match_score",
        "transferability_score",
        mode="before",
    )
    @classmethod
    def _coerce_optional_int(cls, v: object) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None


def parse_skill_list(value: object) -> list[str]:
    """JSON array, slash/comma text, or list[str]."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed: object = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        sep = "/" if "/" in text and "," not in text else ","
        return [part.strip() for part in text.split(sep) if part.strip()]
    return []


def _score(value: object) -> str:
    if value is None or value == "":
        return "?"
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value)


def _clip(text: str, limit: int) -> str:
    raw = (text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[: max(0, limit - 1)].rstrip() + "…"


def _skill_lines(label: str, names: list[str], *, limit: int = 10) -> list[str]:
    if not names:
        return [f"{label}: (none listed)"]
    lines = [f"{label}:"]
    for name in names[:limit]:
        lines.append(f"  • {_clip(name, 160)}")
    omitted = len(names) - limit
    if omitted > 0:
        lines.append(f"  … +{omitted} more")
    return lines


def format_job_telegram_detail(
    job: dict,
    *,
    heading: str = "",
) -> str:
    """Full job card: scores, matched skills, gaps, latest status."""
    data = dict(job)
    data["matched_skills"] = parse_skill_list(
        job.get("matched_skills") or job.get("transferable_strengths")
    )
    data["missing_skills"] = parse_skill_list(
        job.get("missing_skills") or job.get("bridging_gaps")
    )
    card = JobTelegramDetail.model_validate(data)
    lines: list[str] = []
    if heading:
        lines.append(heading)
        lines.append("")
    jid = f"#{card.id} " if card.id is not None else ""
    company = (card.company_name or "Employer").strip()
    title = (card.job_title or "Role").strip()
    lines.append(f"{jid}{company} — {title}")
    status = (card.application_status or "READY").strip() or "READY"
    when = (card.application_status_at or "").strip()
    status_line = f"Status: {application_status_label(status)}"
    if when:
        status_line += f"  ·  {when}"
    lines.append(status_line)
    if card.suitable is not None:
        gate = "Dana ≥80" if card.suitable else "not suitable for Dana → Leo → Clara (need composite ≥80)"
        lines.append(f"suitable={str(card.suitable).lower()}  ·  {gate}")
    lines.append(
        f"Composite {_score(card.match_score)} / 100"
    )
    lines.append(
        f"Hard {_score(card.hard_skill_match_score)}  ·  "
        f"Transfer {_score(card.transferability_score)}"
    )
    lines.append("")
    lines.extend(_skill_lines("Matched", card.matched_skills))
    lines.append("")
    lines.extend(_skill_lines("Gaps", card.missing_skills))
    loc = (card.location_mode or "").strip()
    if loc:
        lines.append("")
        lines.append(f"Location: {loc}")
    salary = (card.salary_range or "").strip()
    if salary:
        lines.append(f"Salary: {salary}")
    why = (card.recommendation_reason or "").strip()
    if why:
        lines.extend(["", "Why:", _clip(why, 700)])
    advice = (card.career_advisory_note or "").strip()
    if advice:
        lines.extend(["", "Note:", _clip(advice, 400)])
    own_note = (card.application_note or "").strip()
    if own_note:
        lines.extend(["", f"Your note: {_clip(own_note, 400)}"])
    employer = (card.employer_update_note or "").strip()
    if employer:
        lines.extend(["", f"Employer: {_clip(employer, 400)}"])
    url = (card.job_url or "").strip()
    if url:
        lines.extend(["", url])
    text = "\n".join(lines).strip()
    if len(text) > 3800:
        return text[:3799].rstrip() + "…"
    return text
