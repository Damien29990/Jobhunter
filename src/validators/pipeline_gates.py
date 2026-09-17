"""Pipeline continuation gates — when to keep Dana/Leo/Clara running.

# Ref: workspace rule — 狀態機轉換封裝為獨立純函數
"""

from __future__ import annotations

# Dana/Leo/Clara pool. # Ref: due_diligence_agent.MIN_MATCH_SCORE
DOWNSTREAM_MIN_SCORE = 80
# Ref: talent_scout_agent.PIVOT_TRANSFERABILITY_FLOOR
DOWNSTREAM_TRANSFER_FLOOR = 85


def passes_dana_composite_gate(composite_score: int, min_score: int = DOWNSTREAM_MIN_SCORE) -> bool:
    """Dana only takes jobs whose stored composite (match_score) meets the floor.

    # Ref: user — min composite score, not transferability OR-bypass
    """
    return int(composite_score or 0) >= int(min_score)


def should_continue_after_rex(
    new_jobs_this_run: int,
    pending_high_score_companies: int,
) -> bool:
    """Dana runs if this scan stored jobs OR SQLite already has a high-score queue.

    Previously Auto stopped when Rex stored 0 *new* URLs even if older high-score
    jobs were still waiting for diligence.

    # Ref: after_rex — do not require this-run inserts
    """
    return int(new_jobs_this_run or 0) > 0 or int(pending_high_score_companies or 0) > 0


def should_continue_after_dana(dossiers_this_run: int, proceed_dossiers: int) -> bool:
    """Leo runs if Dana wrote this turn or PROCEED dossiers already exist."""
    return int(dossiers_this_run or 0) > 0 or int(proceed_dossiers or 0) > 0
