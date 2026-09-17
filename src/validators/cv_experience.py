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


def normalize_experience_list(items: list[Any]) -> list[dict[str, Any]]:
    """Fix reversed dates and sort most-recent role first.

    # Ref: HK CV convention — reverse chronological
    """
    cleaned: list[dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        start, end, present = parse_period_bounds(str(row.get("period") or ""))
        if start or end or present:
            pretty = format_period(start, end, present)
            if pretty:
                row["period"] = pretty
        row["_sort_end"] = end or start or (0, 0)
        row["_sort_start"] = start or (0, 0)
        cleaned.append(row)
    cleaned.sort(key=lambda r: (r["_sort_end"], r["_sort_start"]), reverse=True)
    for row in cleaned:
        row.pop("_sort_end", None)
        row.pop("_sort_start", None)
    return cleaned
