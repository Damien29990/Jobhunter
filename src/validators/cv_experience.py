"""Deterministic CV experience date parse and reverse-chronological order.

# Ref: Milo CV import — do not trust LLM period strings as-is
"""

from __future__ import annotations

import re
from typing import Any

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_PRESENT = re.compile(r"\b(present|now|current|至今|現職)\b", re.I)
_YM = re.compile(
    r"(?:(?P<mon>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)[.\s\-]*)?"
    r"(?P<year>20\d{2}|19\d{2})",
    re.I,
)


def _month_year_to_tuple(month: str | None, year: str) -> tuple[int, int]:
    y = int(year)
    if not month:
        return (y, 1)
    key = month.lower()[:3]
    return (y, _MONTHS.get(key, 1))


def parse_period_bounds(period: str) -> tuple[tuple[int, int] | None, tuple[int, int] | None, bool]:
    """Return (start, end, is_present). Missing bounds are None."""
    text = (period or "").strip()
    if not text:
        return None, None, False
    present = bool(_PRESENT.search(text))
    hits = list(_YM.finditer(text))
    start = end = None
    if hits:
        start = _month_year_to_tuple(hits[0].group("mon"), hits[0].group("year"))
        if len(hits) >= 2:
            end = _month_year_to_tuple(hits[-1].group("mon"), hits[-1].group("year"))
        elif present:
            end = (9999, 12)
        else:
            end = start
    elif present:
        end = (9999, 12)
    if start and end and start > end and not present:
        start, end = end, start
    return start, end, present


def format_period(start: tuple[int, int] | None, end: tuple[int, int] | None, present: bool) -> str:
    def fmt(bound: tuple[int, int]) -> str:
        y, m = bound
        return f"{y:04d}-{m:02d}"

    if not start and not end:
        return ""
    left = fmt(start) if start else ""
    if present:
        right = "Present"
    elif end:
        right = fmt(end)
    else:
        right = ""
    if left and right:
        return f"{left} – {right}"
    return left or right


def iter_experience_roles(job: dict) -> list[dict]:
    """Yield title stints for a company row (promotions live under roles).

    # Ref: same-employer title change — each role has its own period
    """
    if not isinstance(job, dict):
        return []
    nested = job.get("roles")
    if isinstance(nested, list) and any(isinstance(item, dict) for item in nested):
        return [dict(item) for item in nested if isinstance(item, dict)]
    highlights = job.get("highlights")
    skills = job.get("skills_used")
    return [{
        "role": job.get("role") or "",
        "period": job.get("period") or "",
        "highlights": list(highlights) if isinstance(highlights, list) else [],
        "skills_used": list(skills) if isinstance(skills, list) else [],
    }]


def _period_sort_key(period: str) -> tuple[str, tuple[tuple[int, int], tuple[int, int]]]:
    start, end, _present = parse_period_bounds(period)
    pretty = format_period(start, end, _present)
    end_key = end or start or (0, 0)
    start_key = start or (0, 0)
    return pretty, (end_key, start_key)


def normalize_experience_list(items: list[Any]) -> list[dict[str, Any]]:
    """Fix reversed dates and sort most-recent company / title first.

    # Ref: HK CV convention — reverse chronological; promotions share company
    """
    cleaned: list[dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        nested = row.get("roles")
        if isinstance(nested, list) and any(isinstance(item, dict) for item in nested):
            roles: list[dict[str, Any]] = []
            for item in nested:
                if not isinstance(item, dict):
                    continue
                role = dict(item)
                pretty, (end_key, start_key) = _period_sort_key(str(role.get("period") or ""))
                if pretty:
                    role["period"] = pretty
                role["_sort_end"] = end_key
                role["_sort_start"] = start_key
                roles.append(role)
            roles.sort(key=lambda r: (r["_sort_end"], r["_sort_start"]), reverse=True)
            for role in roles:
                role.pop("_sort_end", None)
                role.pop("_sort_start", None)
            row["roles"] = roles
            if roles:
                latest = roles[0]
                row["role"] = latest.get("role")
                row["period"] = latest.get("period")
                row["highlights"] = latest.get("highlights") or []
                row["skills_used"] = latest.get("skills_used") or []
                pretty, (end_key, start_key) = _period_sort_key(str(latest.get("period") or ""))
                row["_sort_end"] = end_key
                row["_sort_start"] = start_key
            else:
                row["_sort_end"] = (0, 0)
                row["_sort_start"] = (0, 0)
        else:
            pretty, (end_key, start_key) = _period_sort_key(str(row.get("period") or ""))
            if pretty:
                row["period"] = pretty
            row["_sort_end"] = end_key
            row["_sort_start"] = start_key
        cleaned.append(row)
    cleaned.sort(key=lambda r: (r["_sort_end"], r["_sort_start"]), reverse=True)
    for row in cleaned:
        row.pop("_sort_end", None)
        row.pop("_sort_start", None)
    return cleaned
