"""Pure-function tests for Milo's shared candidate README.

# Ref: milo_context.py — deterministic path, batch, and Markdown render
"""

from __future__ import annotations

import sys
from pathlib import Path

_AGENTS = Path(__file__).resolve().parents[1] / "src" / "agents"
if str(_AGENTS) not in sys.path:
    sys.path.insert(0, str(_AGENTS))

from milo_context import (
    MiloReadmeDraft,
    fallback_draft,
    live_chat_messages,
    milo_readme_path_for,
    parse_readme_revision,
    redact_pii_for_search,
    render_milo_readme,
    should_refresh_readme,
)


def test_readme_path_for_master_profile() -> None:
    path = milo_readme_path_for(Path("config/master_profile.json"))
    assert path.name == "milo_context.md"
    assert path.parent.name == "config"


def test_readme_path_for_named_profile() -> None:
    path = milo_readme_path_for(Path("config/profiles/alex.json"))
    assert path.name == "alex_milo.md"


def test_refresh_during_first_twenty_then_every_batch() -> None:
    assert should_refresh_readme(0) is False
    assert should_refresh_readme(1) is True
    assert should_refresh_readme(19) is True
    assert should_refresh_readme(20) is True
    assert should_refresh_readme(21) is False
    assert should_refresh_readme(40) is True


def test_has_new_chat_watermark() -> None:
    from milo_context import has_new_chat_since_compress, last_compress_path_for
    assert has_new_chat_since_compress({}, 0) is True
    profile = {"milo_compress_state": {"live_message_count": 4}}
    assert has_new_chat_since_compress(profile, 4) is False
    assert has_new_chat_since_compress(profile, 6) is True
    path = last_compress_path_for(Path("config/master_profile.json"))
    assert path.name == "milo_last_compress.md"


def test_live_chat_drops_system_rows() -> None:
    rows = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "system", "content": "[COMPRESSED] x"},
    ]
    live = live_chat_messages(rows)
    assert len(live) == 2
    assert all(m["role"] != "system" for m in live)


def test_render_includes_skill_sections() -> None:
    draft = MiloReadmeDraft(
        who="Backend engineer pivoting to PropTech.",
        career_context="Seconded to a ConTech IoT team.",
        transferable_skills=["FastAPI", "PostgreSQL"],
        target_industries=["PropTech"],
        role_archetypes=["Platform engineer"],
        deal_breakers=["Must stay in Hong Kong"],
        guidance_for_agents="Broaden search into utilities.",
    )
    md = render_milo_readme(
        draft,
        updated_at="2026-09-13T21:00:00+08:00",
        live_message_count=20,
        revision=2,
        source="chat_batch_20",
    )
    assert "name: milo-candidate-context" in md
    assert "revision: 2" in md
    assert "FastAPI" in md
    assert "Must stay in Hong Kong" in md
    assert parse_readme_revision(md) == 2


def test_fallback_draft_uses_profile_skills() -> None:
    profile = {
        "basics": {"name": "Damien", "target_roles": ["Backend Engineer"]},
        "technical_skills": {"backend": ["Python", "FastAPI"]},
        "acceptance_context": {
            "core_transferable_skills": ["IoT telemetry"],
            "target_industries": ["ConTech"],
            "executive_narrative": "Story.",
        },
    }
    draft = fallback_draft(profile, chat_excerpt="user: I like PropTech")
    assert "IoT telemetry" in draft.transferable_skills
    assert "Python" in draft.transferable_skills
    assert "PropTech" in draft.career_context


def test_redact_pii_for_rex() -> None:
    text = "Email me at a.b@example.com or +852 1234 5678"
    cleaned = redact_pii_for_search(text)
    assert "@" not in cleaned
    assert "1234" not in cleaned
    assert "[email]" in cleaned
    assert "[phone]" in cleaned
