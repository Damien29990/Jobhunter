"""Deterministic score & verdict gates — self-contained, no heavy imports.

These constants and pure functions mirror the agent modules exactly. They are
defined locally (not imported) so the dashboard API can start with ONLY
fastapi/uvicorn/pydantic installed — it does NOT need openai / tavily /
sqlite-vec / httpx, and does NOT load the sqlite_vec native extension.

# Ref: workspace ConTech/IoT rule — thresholds as pure functions, no LLM
# guessing, no Any. Source of truth for each value is noted; if the agent
# module ever changes a value, update it here too.

Why not import? talent_scout_agent.py pulls in `sqlite_vec` (native ext),
`openai`, `tavily`, `httpx` at top level. Importing it just to read 3
constants would make the API fail to start whenever those deps are missing
or the native extension fails to load. The agents themselves run as
subprocesses (via agent_runner.py) in the jobhunter env that has all deps.
"""
from __future__ import annotations

# --- Constants (mirror the agent modules; see source refs) ---

# talent_scout_agent.py:292
PIVOT_TRANSFERABILITY_FLOOR: int = 85

# talent_scout_agent.py:293-294
COMPOSITE_HARD_SKILL_WEIGHT: float = 0.55
COMPOSITE_TRANSFERABILITY_WEIGHT: float = 0.45

# talent_scout_agent_2.py:41
AGENT1_DEFAULT_MIN_SCORE: int = 75

# due_diligence_agent.py:67, cv_generator_agent.py:37, cert_matcher_agent.py:41
MIN_MATCH_SCORE: int = 80

# cert_matcher_agent.py:42, cv_generator_agent.py:39
STATUS_GENERATED: str = "MATERIALS_GENERATED"
# cv_generator_agent.py:59
STATUS_RENDERED: str = "MATERIALS_RENDERED"

DANA_JOB_SELECT_STAGES: tuple[str, ...] = ("discovered", "vetted")

# --- Derived gate constants ---

# Agent 2 candidate pool gate (list_companies_pending_diligence)
# Composite only — transferability ≥ 85 does not admit a job to Dana.
AGENT2_POOL_MIN_SCORE: int = 80
AGENT2_POOL_TRANSFER_FLOOR: int = PIVOT_TRANSFERABILITY_FLOOR  # unused by Dana queue

# Agent 3 final gate (list_vetted_jobs)
AGENT3_CV_MIN_SCORE: int = 80
AGENT3_CV_REQUIRED_VERDICT: str = "PROCEED"

# Agent 4 gate (list_ready_jobs)
AGENT4_MIN_SCORE: int = MIN_MATCH_SCORE  # 80
AGENT4_REQUIRED_CV_STATUS: str = STATUS_GENERATED  # MATERIALS_GENERATED

# Composite weighting (do not re-derive in the frontend)
HARD_WEIGHT: float = COMPOSITE_HARD_SKILL_WEIGHT  # 0.55
TRANSFER_WEIGHT: float = COMPOSITE_TRANSFERABILITY_WEIGHT  # 0.45

# Kanban column thresholds (Discovered column)
DISCOVERED_MIN_SCORE: int = AGENT1_DEFAULT_MIN_SCORE  # 75
DISCOVERED_TRANSFER_FLOOR: int = PIVOT_TRANSFERABILITY_FLOOR  # 85

# Main dashboard hides these; they stay in SQLite for agent recall.
# Ref: user — filter scores < 35; unconsiderable is a user status, not a delete
DASHBOARD_MIN_DISPLAY_SCORE: int = 35
USER_STATUS_UNCONSIDERABLE: str = "UNCONSIDERABLE"


# --- Pure functions (mirror the agent modules exactly) ---

def compute_composite_match_score(
    hard_skill_score: int, transferability_score: int
) -> int:
    """Weighted dual-score. Mirrors talent_scout_agent.compute_composite_match_score.

    # Ref: career-architect matrix — 55% hard-skill / 45% transferability
    """
    hard = max(0, min(100, int(hard_skill_score)))
    transfer = max(0, min(100, int(transferability_score)))
    blended = (
        COMPOSITE_HARD_SKILL_WEIGHT * hard
        + COMPOSITE_TRANSFERABILITY_WEIGHT * transfer
    )
    return max(0, min(100, int(round(blended))))


def passes_dual_score_gate(
    composite_score: int,
    transferability_score: int,
    min_score: int = AGENT1_DEFAULT_MIN_SCORE,
    pivot_floor: int = PIVOT_TRANSFERABILITY_FLOOR,
) -> bool:
    """Keep strong matches and high-transfer pivots.

    # Ref: dual-score gate — composite >= min_score OR transferability >= 85
    Mirrors talent_scout_agent.passes_dual_score_gate.
    """
    return composite_score >= min_score or transferability_score >= pivot_floor


def passes_dana_composite_gate(
    composite_score: int, min_score: int = AGENT2_POOL_MIN_SCORE
) -> bool:
    """Dana pool: stored match_score (composite) must meet the minimum.

    # Ref: user — no transferability bypass into due diligence
    """
    return int(composite_score or 0) >= int(min_score)


def normalize_verdict(value: str) -> str:
    """Normalize a verdict string to PROCEED / AVOID.

    Mirrors due_diligence_agent.normalize_verdict exactly.
    Only exact 'PROCEED' (after normalization) is a pass.
    """
    upper = (value or "").upper()
    if "AVOID" in upper:
        return "AVOID"
    return "PROCEED"


def passes_absolute_deal_breakers(
    jd_text: str,
    deal_breakers: list[str] | None,
) -> tuple[bool, str]:
    """Check if JD text contains any absolute deal-breaker phrase.

    Returns (passed, reason). If passed=True, the job is NOT blocked.
    This is the ONLY hard filter Milo applies — minimal, not a blacklist.
    Case-insensitive substring match. Empty deal_breakers = always pass.

    # Ref: Milo design — only absolute_deal_breakers act as hard filter.
    """
    if not deal_breakers:
        return True, ""
    text_lower = (jd_text or "").lower()
    for phrase in deal_breakers:
        if phrase and phrase.strip() and phrase.strip().lower() in text_lower:
            return False, phrase.strip()
    return True, ""


def kanban_column(
    match_score: int | None,
    cv_status: str | None,
    application_ready: bool | None,
    vetting_verdict: str | None,
) -> str:
    """Kanban column for an active job. Mirrors PipelineKanban.classify.

    # Ref: frontend/src/components/PipelineKanban.jsx classify()
    """
    if application_ready:
        return "applied"
    status = (cv_status or "").strip()
    if status in {STATUS_GENERATED, STATUS_RENDERED}:
        return "materials"
    if (vetting_verdict or "").strip():
        return "vetted"
    if int(match_score or 0) >= AGENT2_POOL_MIN_SCORE:
        return "vetting"
    return "discovered"


def is_unconsiderable(user_status: str | None) -> bool:
    """True when the user marked the job as not for their own pipeline.

    Agents may still read the row. # Ref: USER_STATUS_UNCONSIDERABLE
    """
    return (user_status or "").strip().upper() == USER_STATUS_UNCONSIDERABLE


def shelf_bucket(
    match_score: int | None,
    expired: bool | None,
    user_status: str | None,
) -> str | None:
    """Which shelf section a job belongs in, or None if it stays on the kanban.

    Exclusive order: unconsiderable → expired → low_score.
    # Ref: DASHBOARD_MIN_DISPLAY_SCORE
    """
    if is_unconsiderable(user_status):
        return "unconsiderable"
    if bool(expired):
        return "expired"
    score = int(match_score) if match_score is not None else 0
    if score < DASHBOARD_MIN_DISPLAY_SCORE:
        return "low_score"
    return None


__all__ = [
    "PIVOT_TRANSFERABILITY_FLOOR",
    "COMPOSITE_HARD_SKILL_WEIGHT",
    "COMPOSITE_TRANSFERABILITY_WEIGHT",
    "HARD_WEIGHT",
    "TRANSFER_WEIGHT",
    "AGENT1_DEFAULT_MIN_SCORE",
    "AGENT2_POOL_MIN_SCORE",
    "AGENT2_POOL_TRANSFER_FLOOR",
    "AGENT3_CV_MIN_SCORE",
    "AGENT3_CV_REQUIRED_VERDICT",
    "AGENT4_MIN_SCORE",
    "AGENT4_REQUIRED_CV_STATUS",
    "MIN_MATCH_SCORE",
    "STATUS_GENERATED",
    "STATUS_RENDERED",
    "DANA_JOB_SELECT_STAGES",
    "DISCOVERED_MIN_SCORE",
    "DISCOVERED_TRANSFER_FLOOR",
    "DASHBOARD_MIN_DISPLAY_SCORE",
    "USER_STATUS_UNCONSIDERABLE",
    "is_unconsiderable",
    "kanban_column",
    "shelf_bucket",
    "compute_composite_match_score",
    "passes_dual_score_gate",
    "passes_dana_composite_gate",
    "normalize_verdict",
    "passes_absolute_deal_breakers",
]
