"""Clara post-application follow-up — user-marked status, no LLM.

# Ref: Agent 4 — after application_ready, humans track the employer reply
"""

from __future__ import annotations

from typing import Optional

ApplicationStatus = str

STATUS_READY = "READY"
STATUS_APPLIED = "APPLIED"
STATUS_AWAITING = "AWAITING"
STATUS_EMPLOYER_UPDATE = "EMPLOYER_UPDATE"
STATUS_INTERVIEW = "INTERVIEW"
STATUS_OFFER = "OFFER"
STATUS_REJECTED = "REJECTED"
STATUS_WITHDRAWN = "WITHDRAWN"

APPLICATION_STATUSES: tuple[str, ...] = (
    STATUS_READY,
    STATUS_APPLIED,
    STATUS_AWAITING,
    STATUS_EMPLOYER_UPDATE,
    STATUS_INTERVIEW,
    STATUS_OFFER,
    STATUS_REJECTED,
    STATUS_WITHDRAWN,
)

# User still needs to act (wait, reply, or attend).
OPEN_FOLLOW_UP: frozenset[str] = frozenset(
    {
        STATUS_APPLIED,
        STATUS_AWAITING,
        STATUS_EMPLOYER_UPDATE,
        STATUS_INTERVIEW,
    }
)

TERMINAL_STATUSES: frozenset[str] = frozenset(
    {STATUS_OFFER, STATUS_REJECTED, STATUS_WITHDRAWN}
)


def normalize_application_status(raw: Optional[str]) -> str:
    """Empty / unknown → READY. # Ref: Clara pack stamped but not yet submitted."""
    text = str(raw or "").strip().upper().replace("-", "_").replace(" ", "_")
    if text in APPLICATION_STATUSES:
        return text
    return STATUS_READY


def follow_up_needed(status: Optional[str], application_ready: bool | None) -> bool:
    """True when Clara's pack is ready and the user is still in an open stage."""
    if not application_ready:
        return False
    return normalize_application_status(status) in OPEN_FOLLOW_UP


def skip_listing_expiry_check(status: Optional[str]) -> bool:
    """Do not HTTP-expire listings the user already applied to or closed.

    After apply, job boards often 404, login-wall, or drop the title from the
    page; listing_sweep would wrongly shelf those rows. READY packs still scan.
    # Ref: listing_sweep / Dana check_listing_still_open
    """
    normalized = normalize_application_status(status)
    if normalized == STATUS_READY:
        return False
    return normalized in APPLICATION_STATUSES


def default_status_when_pack_ready(existing: Optional[str]) -> str:
    """Keep a later user status; stamp READY the first time Clara finishes.

    # Ref: cert_matcher_agent._update_status
    """
    text = str(existing or "").strip()
    if text:
        return normalize_application_status(text)
    return STATUS_READY
