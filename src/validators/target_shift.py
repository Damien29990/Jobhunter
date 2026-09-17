"""Deterministic target-job shift gates for Milo.

Milo may retrieve stored job_postings only when the user made a *direct*
and *major* change to target industries / role types. Thresholds live here
so the LLM cannot invent when to pull jobs.

# Ref: workspace rule — 數值閾值封裝為獨立純函數
"""

from __future__ import annotations

import re
from typing import Mapping, Optional, Sequence

# Jaccard at or below this = major shift. # Ref: Milo job-recall gate
MAJOR_JACCARD_MAX = 0.45
# Added or dropped distinct terms that also count as a major pivot.
MIN_ADDED_TERMS = 2
MIN_REMOVED_TERMS = 2
# First-time stated targets: require at least this many terms.
MIN_FIRST_STATEMENT_TERMS = 2
MAX_SQL_TERMS = 8
MAX_TERM_LEN = 48

_DIRECT_MARKERS: tuple[str, ...] = (
    "change my target",
    "new target",
    "from now on",
    "switch to",
    "instead of",
    "no longer",
    "don't want",
    "do not want",
    "i want to target",
    "only look for",
    "only apply",
    "pivot to",
    "目標改",
    "改為",
    "改做",
    "轉做",
    "轉去",
    "不再找",
    "不要再",
    "唔再做",
    "唔再搵",
    "只找",
    "只做",
    "只搵",
    "轉型",
    "轉行",
)


def normalize_target_term(term: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace.

    # Ref: target term identity for Jaccard
    """
    text = (term or "").strip().lower()
    text = re.sub(r"[^\w\u4e00-\u9fff+.#]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def unique_target_terms(terms: Sequence[str]) -> list[str]:
    """Deduplicate target terms while keeping first-seen normalized form."""
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in terms:
        key = normalize_target_term(str(raw))
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


def collect_target_terms(
    profile: Mapping[str, object],
    extracted: Optional[Mapping[str, object]] = None,
) -> list[str]:
    """Gather industries and role archetypes from profile + this-turn facts.

    # Ref: PAC + stated_targets + extracted_facts
    """
    buckets: list[object] = []
    pac = profile.get("acceptance_context")
    if isinstance(pac, Mapping):
        buckets.append(pac.get("target_industries"))
        buckets.append(pac.get("role_archetypes"))
    stated = profile.get("stated_targets")
    if isinstance(stated, Mapping):
        buckets.append(stated.get("industries"))
        buckets.append(stated.get("roles"))
    basics = profile.get("basics")
    if isinstance(basics, Mapping):
        buckets.append(basics.get("target_roles"))
    if extracted:
        buckets.append(extracted.get("target_industries"))
        buckets.append(extracted.get("role_archetypes"))
        buckets.append(extracted.get("target_roles"))
    raw: list[str] = []
    for bucket in buckets:
        if isinstance(bucket, str) and bucket.strip():
            raw.append(bucket)
        elif isinstance(bucket, list):
            raw.extend(str(item) for item in bucket if item)
    return unique_target_terms(raw)


def is_direct_target_statement(
    extracted: Optional[Mapping[str, object]],
    user_message: str,
) -> bool:
    """True only if this user turn explicitly changes target jobs.

    # Ref: user rule — retrieve jobs only on a big *direct* target change
    """
    facts = extracted or {}
    for key in ("target_industries", "role_archetypes", "target_roles"):
        value = facts.get(key)
        if isinstance(value, list) and any(str(item).strip() for item in value):
            return True
        if isinstance(value, str) and value.strip():
            return True
    text = (user_message or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _DIRECT_MARKERS)


def is_major_target_shift(old_terms: Sequence[str], new_terms: Sequence[str]) -> bool:
    """Compare normalized term sets. Empty new set is never a retrieve trigger.

    # Ref: Jaccard / added / removed thresholds
    """
    old_set = set(unique_target_terms(old_terms))
    new_set = set(unique_target_terms(new_terms))
    if not new_set:
        return False
    if new_set == old_set:
        return False
    if not old_set:
        return len(new_set) >= MIN_FIRST_STATEMENT_TERMS
    union = old_set | new_set
    inter = old_set & new_set
    jaccard = len(inter) / len(union)
    added = new_set - old_set
    removed = old_set - new_set
    return (
        jaccard <= MAJOR_JACCARD_MAX
        or len(added) >= MIN_ADDED_TERMS
        or len(removed) >= MIN_REMOVED_TERMS
    )


def should_retrieve_stored_jobs(
    *,
    old_terms: Sequence[str],
    new_terms: Sequence[str],
    extracted: Optional[Mapping[str, object]],
    user_message: str,
) -> bool:
    """Single gate: direct statement AND major shift.

    # Ref: Milo job recall — both conditions required
    """
    return is_direct_target_statement(extracted, user_message) and is_major_target_shift(
        old_terms, new_terms
    )


def matching_job_where(terms: Sequence[str]) -> tuple[str, list[str]]:
    """Build a parameterized WHERE clause for job_postings overlap.

    # Ref: SQL LIKE on title / industry / snippet — no LLM ranking
    """
    keys = unique_target_terms(terms)[:MAX_SQL_TERMS]
    clauses: list[str] = []
    params: list[str] = []
    for key in keys:
        if len(key) > MAX_TERM_LEN:
            key = key[:MAX_TERM_LEN]
        like = f"%{key.replace('%', '').replace('_', '')}%"
        clauses.append(
            "("
            "LOWER(COALESCE(job_title, '')) LIKE ? OR "
            "LOWER(COALESCE(target_industry, '')) LIKE ? OR "
            "LOWER(COALESCE(jd_snippet, '')) LIKE ? OR "
            "LOWER(COALESCE(company_name, '')) LIKE ?"
            ")"
        )
        params.extend([like, like, like, like])
    if not clauses:
        return "", []
    return "(" + " OR ".join(clauses) + ")", params


def format_jobs_for_milo(jobs: Sequence[Mapping[str, object]]) -> str:
    """Deterministic bilingual block appended to Milo's reply.

    # Ref: stored job_postings recall
    """
    if not jobs:
        return (
            "\n\n——\n"
            "你剛大幅改了目標職位。資料庫暫時沒有符合新方向的舊職缺，"
            "等 Rex 下次掃描後會再寫入。\n"
            "You just made a major target-job change. No stored listings match yet; "
            "Rex will add new ones on the next scan."
        )
    lines = [
        "\n\n——",
        "你剛大幅改了目標職位，以下是資料庫裡可能相關的職缺（不會每次閒聊都列出）：",
        "Major target change detected. Stored jobs that may fit:",
    ]
    for job in jobs:
        company = str(job.get("company_name") or "Employer")
        title = str(job.get("job_title") or "Role")
        score = job.get("match_score")
        industry = str(job.get("target_industry") or "")
        url = str(job.get("job_url") or "")
        score_bit = f" score={score}" if score is not None else ""
        industry_bit = f" · {industry}" if industry else ""
        lines.append(f"• [{company}] {title}{score_bit}{industry_bit}")
        if url:
            lines.append(f"  {url}")
    return "\n".join(lines)


def merge_stated_targets(
    profile: dict,
    extracted: Optional[Mapping[str, object]],
) -> dict:
    """Write extracted industries/roles onto profile['stated_targets']."""
    facts = extracted or {}
    stated = profile.setdefault("stated_targets", {})
    if not isinstance(stated, dict):
        stated = {}
        profile["stated_targets"] = stated

    def _extend(bucket_key: str, fact_key: str) -> None:
        incoming = facts.get(fact_key)
        values: list[str] = []
        if isinstance(incoming, list):
            values = [str(item).strip() for item in incoming if str(item).strip()]
        elif isinstance(incoming, str) and incoming.strip():
            values = [incoming.strip()]
        if not values:
            return
        current = stated.get(bucket_key) or []
        if not isinstance(current, list):
            current = []
        merged = unique_target_terms([*(str(x) for x in current), *values])
        stated[bucket_key] = merged

    _extend("industries", "target_industries")
    _extend("roles", "role_archetypes")
    _extend("roles", "target_roles")
    return profile
