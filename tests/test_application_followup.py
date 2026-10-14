"""Clara application follow-up status machine (no DB)."""

from __future__ import annotations

import sys
from pathlib import Path

_VALIDATORS = Path(__file__).resolve().parents[1] / "src" / "validators"
if str(_VALIDATORS) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS))

from application_followup import (
    STATUS_APPLIED,
    STATUS_READY,
    default_status_when_pack_ready,
    follow_up_needed,
    normalize_application_status,
    skip_listing_expiry_check,
)


def test_applied_skips_listing_expiry() -> None:
    assert skip_listing_expiry_check("APPLIED") is True
    assert skip_listing_expiry_check("INTERVIEW") is True
    assert skip_listing_expiry_check("READY") is False
    assert skip_listing_expiry_check(None) is False


def test_normalize_unknown_is_ready() -> None:
    assert normalize_application_status(None) == STATUS_READY
    assert normalize_application_status("applied") == STATUS_APPLIED


def test_follow_up_only_after_pack_and_open_stage() -> None:
    assert follow_up_needed(STATUS_APPLIED, True) is True
    assert follow_up_needed(STATUS_APPLIED, False) is False
    assert follow_up_needed("REJECTED", True) is False
    assert follow_up_needed("READY", True) is False


def test_clara_does_not_reset_applied() -> None:
    assert default_status_when_pack_ready("APPLIED") == STATUS_APPLIED
    assert default_status_when_pack_ready("") == STATUS_READY
