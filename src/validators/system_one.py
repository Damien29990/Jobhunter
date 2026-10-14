"""System One decisions — fast structured yes/no, no prose generation.

# Ref: Kahneman System 1 / TypeSafe System One — bounded semantic judgment
# Hard rules stay heuristic. Semantic JD gating can call Laya when configured.
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from laya_client import ask_noul, load_laya_config

HK_TZ = ZoneInfo("Asia/Hong_Kong")

# Minimum JD body before spending DeepSeek on scoring.
# Ref: pasted-URL ingest uses ~80 chars as unreadable
MIN_JD_CHARS_TO_EVALUATE = 80

# Dossier older than this is stale enough to re-run Dana.
# Ref: research_search_cache SEARCH_CACHE_MAX_AGE_DAYS = 14
DOSSIER_STALE_DAYS = 14

# Dana confidence is 0–100. Below this, re-run even if the dossier is young.
DOSSIER_RERUN_CONFIDENCE_FLOOR = 50

# Laya noul must meet this to spend DeepSeek on a listing.
# Ref: System One — threshold is a constant, never guessed by the model
LAYA_EVALUATE_THRESHOLD: float = 0.55

_EVALUATE_INSTRUCTIONS = (
    "Is this a real paid Hong Kong IT or engineering job posting that is "
    "worth spending an LLM score on? Answer no for academic programmes, "
    "unpaid internships, non-Hong-Kong roles, non-IT ads, or empty listings."
)

_AUDIT_MAX = 8
_audit_lock = threading.Lock()
_audit: deque[SystemOneAudit] = deque(maxlen=_AUDIT_MAX)

_HK_HINTS = (
    "hong kong", "hongkong", "香港", "kowloon", "九龍", "新界",
    "hk.jobsdb", "ctgoodjobs", "hkstp", "talentjobseeker", "work from hong",
)
_ROLE_HINTS = (
    "engineer", "developer", "analyst", "architect", "scientist",
    "researcher", "data science", "manager", "specialist", "consultant",
    "lead", "sre", "devops",
    "programmer", "officer", "intern", "工程師", "開發", "分析", "架構", "研究員",
)


class SystemOneDecision(BaseModel):
    """Typed System One answer. Software branches on proceed; reason is audit-only.

    # Ref: TypeSafe Jev — unstructured state in, typed decision out
    """

    proceed: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    backend: Literal["heuristic", "laya"] = "heuristic"


class SystemOneAudit(BaseModel):
    """Last System One calls for the dashboard. Times are Asia/Hong_Kong.

    # Ref: workspace timezone Asia/Hong_Kong ISO 8601
    """

    gate: str
    title: str = ""
    proceed: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    backend: Literal["heuristic", "laya"]
    decided_at: str


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


def _remember(gate: str, title: str, decision: SystemOneDecision) -> SystemOneDecision:
    row = SystemOneAudit(
        gate=gate,
        title=(title or "")[:80],
        proceed=decision.proceed,
        confidence=decision.confidence,
        reason=decision.reason,
        backend=decision.backend,
        decided_at=datetime.now(HK_TZ).isoformat(timespec="seconds"),
    )
    with _audit_lock:
        _audit.append(row)
    return decision


def recent_decisions() -> list[SystemOneAudit]:
    with _audit_lock:
        return list(_audit)


def status_snapshot() -> dict[str, object]:
    """Dashboard-facing Laya / System One status. No secrets.

    # Ref: /api/system-one
    """
    cfg = load_laya_config()
    return {
        "name": "Laya",
        "role": "System One",
        "backend": "laya" if cfg.prefer_laya else "heuristic",
        "configured": bool(cfg.url),
        "model": cfg.model,
        "threshold": LAYA_EVALUATE_THRESHOLD,
        "last_decisions": [row.model_dump() for row in recent_decisions()],
    }


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
    Short / empty JD never reaches Laya. Semantic yes/no may use Laya noul.
    # Ref: Rex — store JD first, then System One gates the LLM score
    """
    if user_supplied:
        return _remember(
            "evaluate_jd",
            title,
            SystemOneDecision(proceed=True, confidence=1.0, reason="user-supplied listing"),
        )
    if already_scored:
        return _remember(
            "evaluate_jd",
            title,
            SystemOneDecision(proceed=False, confidence=0.95, reason="already scored"),
        )
    blob = f"{title or ''} {content or ''} {url or ''}".lower()
    text = (content or "").strip()
    if len(text) < MIN_JD_CHARS_TO_EVALUATE:
        return _remember(
            "evaluate_jd",
            title,
            SystemOneDecision(proceed=False, confidence=0.85, reason="JD text too short to score"),
        )

    state = f"title: {title or ''}\nurl: {url or ''}\njd: {text}"
    noul = ask_noul(state, _EVALUATE_INSTRUCTIONS, name="evaluate")
    if noul is not None:
        proceed = noul >= LAYA_EVALUATE_THRESHOLD
        return _remember(
            "evaluate_jd",
            title,
            SystemOneDecision(
                proceed=proceed,
                confidence=noul if proceed else (1.0 - noul),
                reason=f"Laya noul={noul:.2f} (threshold {LAYA_EVALUATE_THRESHOLD})",
                backend="laya",
            ),
        )

    role_hit = any(hint in blob for hint in _ROLE_HINTS)
    hk_hit = any(hint in blob for hint in _HK_HINTS)
    if not role_hit:
        return _remember(
            "evaluate_jd",
            title,
            SystemOneDecision(proceed=False, confidence=0.7, reason="no IT/role noun in title or JD"),
        )
    if not hk_hit:
        return _remember(
            "evaluate_jd",
            title,
            SystemOneDecision(proceed=False, confidence=0.6, reason="no Hong Kong signal in JD or URL"),
        )
    return _remember(
        "evaluate_jd",
        title,
        SystemOneDecision(
            proceed=True,
            confidence=0.8,
            reason="JD looks like a Hong Kong IT vacancy",
        ),
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
    Existing dossiers are kept: low confidence and age do not re-spend Tavily.
    Only a newer stored listing (or force) re-opens research.
    # Ref: Dana — do not loop past researched employers
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
