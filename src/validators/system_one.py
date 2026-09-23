"""System One decisions — fast structured yes/no, no prose generation.

# Ref: Kahneman System 1 / TypeSafe System One — bounded semantic judgment
# Jobhunter uses a calibrated heuristic until a Jev/Laya key is configured.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

HK_TZ = ZoneInfo("Asia/Hong_Kong")

# Minimum JD body before spending DeepSeek on scoring.
# Ref: pasted-URL ingest uses ~80 chars as unreadable
MIN_JD_CHARS_TO_EVALUATE = 80

# Dossier older than this is stale enough to re-run Dana.
# Ref: research_search_cache SEARCH_CACHE_MAX_AGE_DAYS = 14
DOSSIER_STALE_DAYS = 14

# Dana confidence is 0–100. Below this, re-run even if the dossier is young.
DOSSIER_RERUN_CONFIDENCE_FLOOR = 50

_HK_HINTS = (
    "hong kong", "hongkong", "香港", "kowloon", "九龍", "新界",
    "hk.jobsdb", "ctgoodjobs", "hkstp", "talentjobseeker", "work from hong",
)
_ROLE_HINTS = (
    "engineer", "developer", "analyst", "architect", "scientist",
    "manager", "specialist", "consultant", "lead", "sre", "devops",
    "programmer", "officer", "intern", "工程師", "開發", "分析", "架構",
)


class SystemOneDecision(BaseModel):
    """Typed System One answer. Software branches on proceed; reason is audit-only.

    # Ref: TypeSafe Jev — unstructured state in, typed decision out
    """

    proceed: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    backend: Literal["heuristic"] = "heuristic"


def _parse_hk(stamp: Optional[str]) -> Optional[datetime]:
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=HK_TZ)
    return parsed.astimezone(HK_TZ)


def _age_days(stamp: Optional[str]) -> Optional[int]:
    parsed = _parse_hk(stamp)
    if parsed is None:
        return None
    return (datetime.now(HK_TZ) - parsed).days


def should_evaluate_jd(
    *,
    title: str,
    content: str,
    url: str = "",
    already_scored: bool = False,
    user_supplied: bool = False,
) -> SystemOneDecision:
    """Decide whether Rex should spend DeepSeek on this stored listing.

    User-pasted URLs always evaluate. Already-scored rows skip.
    # Ref: Rex — store JD first, then System One gates the LLM score
    """
    if user_supplied:
        return SystemOneDecision(
            proceed=True,
            confidence=1.0,
            reason="user-supplied listing",
        )
    if already_scored:
        return SystemOneDecision(
            proceed=False,
            confidence=0.95,
            reason="already scored",
        )
    blob = f"{title or ''} {content or ''} {url or ''}".lower()
    text = (content or "").strip()
    if len(text) < MIN_JD_CHARS_TO_EVALUATE:
        return SystemOneDecision(
            proceed=False,
            confidence=0.85,
            reason="JD text too short to score",
        )
    role_hit = any(hint in blob for hint in _ROLE_HINTS)
    hk_hit = any(hint in blob for hint in _HK_HINTS)
    if not role_hit:
        return SystemOneDecision(
            proceed=False,
            confidence=0.7,
            reason="no IT/role noun in title or JD",
        )
    if not hk_hit:
        return SystemOneDecision(
            proceed=False,
            confidence=0.6,
            reason="no Hong Kong signal in JD or URL",
        )
    return SystemOneDecision(
        proceed=True,
        confidence=0.8,
        reason="JD looks like a Hong Kong IT vacancy",
    )


def should_rerun_dossier(
    *,
    has_dossier: bool,
    dossier_updated_at: Optional[str] = None,
    dossier_confidence: Optional[int] = None,
    newest_job_created_at: Optional[str] = None,
    force: bool = False,
) -> SystemOneDecision:
    """Decide whether Dana should re-run Tavily + DeepSeek for an employer.

    Manual --force / job-id force_refresh always proceeds.
    # Ref: Dana — skip a fresh high-confidence dossier unless new jobs arrived
    """
    if force:
        return SystemOneDecision(
            proceed=True,
            confidence=1.0,
            reason="manual force refresh",
        )
    if not has_dossier:
        return SystemOneDecision(
            proceed=True,
            confidence=1.0,
            reason="no dossier yet",
        )
    age = _age_days(dossier_updated_at)
    if age is not None and age >= DOSSIER_STALE_DAYS:
        return SystemOneDecision(
            proceed=True,
            confidence=0.85,
            reason=f"dossier is {age} days old",
        )
    conf = int(dossier_confidence) if dossier_confidence is not None else 0
    if conf < DOSSIER_RERUN_CONFIDENCE_FLOOR:
        return SystemOneDecision(
            proceed=True,
            confidence=0.75,
            reason=f"dossier confidence {conf} below {DOSSIER_RERUN_CONFIDENCE_FLOOR}",
        )
    job_ts = _parse_hk(newest_job_created_at)
    dossier_ts = _parse_hk(dossier_updated_at)
    if job_ts is not None and (dossier_ts is None or job_ts > dossier_ts):
        return SystemOneDecision(
            proceed=True,
            confidence=0.8,
            reason="newer job listing since last dossier",
        )
    return SystemOneDecision(
        proceed=False,
        confidence=0.8,
        reason="fresh dossier, no newer listings",
    )
