"""Deterministic CV project shortlist and layout order.

# Ref: Leo CV — 2-4 JD-relevant projects; side projects last
"""

from __future__ import annotations

import re

MAX_CV_PROJECTS = 4
MIN_CV_PROJECTS = 2
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9+.#-]{1,}")


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN.finditer(text or "")}


def project_relevance_score(project: dict[str, object], jd_text: str) -> int:
    """Count overlapping tokens between a project and the JD.

    # Ref: no LLM guessing — tech_stack hits weigh more than prose
    """
    hay = _tokens(jd_text)
    if not hay:
        return 0
    blob = " ".join(
        [
            str(project.get("name") or ""),
            str(project.get("role") or ""),
            str(project.get("description") or ""),
            str(project.get("employer") or ""),
            " ".join(str(item) for item in (project.get("tech_stack") or [])),
        ]
    )
    score = 0
    for token in _tokens(blob):
        if token in hay:
            score += 1
    for item in project.get("tech_stack") or []:
        tech = str(item).strip().lower()
        if tech and tech in (jd_text or "").lower():
            score += 2
    return score


def select_and_order_cv_projects(
    projects: list[dict[str, object]],
    jd_text: str,
    max_count: int = MAX_CV_PROJECTS,
) -> list[dict[str, object]]:
    """Keep 2-4 JD-related projects: work first, side projects last.

    Related work fills first. Unrelated work is not copied just to pad to 4.
    Side projects only fill leftover slots (or the minimum if work is thin).
    """
    cap = max(1, int(max_count))
    rows = [dict(item) for item in projects if isinstance(item, dict)]
    work = [item for item in rows if not bool(item.get("is_side_project"))]
    side = [item for item in rows if bool(item.get("is_side_project"))]
    work.sort(key=lambda item: project_relevance_score(item, jd_text), reverse=True)
    side.sort(key=lambda item: project_relevance_score(item, jd_text), reverse=True)

    picked: list[dict[str, object]] = []

    def _take(source: list[dict[str, object]], *, related_only: bool, stop_at: int) -> None:
        for item in source:
            if len(picked) >= stop_at or item in picked:
                continue
            score = project_relevance_score(item, jd_text)
            if related_only and score <= 0:
                continue
            picked.append(item)

    _take(work, related_only=True, stop_at=cap)
    floor = min(MIN_CV_PROJECTS, len(rows), cap)
    _take(work, related_only=False, stop_at=floor)
    _take(side, related_only=True, stop_at=cap)
    _take(side, related_only=False, stop_at=floor)
    work_out = [item for item in picked if not bool(item.get("is_side_project"))]
    side_out = [item for item in picked if bool(item.get("is_side_project"))]
    return work_out + side_out
