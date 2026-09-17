"""Milo skill-like README — compressed CV + chat for downstream agents.

Ollama (or a deterministic fallback) fills structured sections; Markdown
rendering is a pure function so Rex / Dana / Leo / Clara share one file.

# Ref: workspace rule — Pydantic v2, 禁用 Any; Asia/Hong_Kong ISO 8601;
#      deterministic render separate from LLM extraction.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator

HK_TZ = ZoneInfo("Asia/Hong_Kong")
CHAT_README_BATCH = 20
README_MAX_CHARS = 6000

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-()]{7,}\d")
_REVISION_RE = re.compile(r"^revision:\s*(\d+)\s*$", re.MULTILINE)


class MiloReadmeDraft(BaseModel):
    """Structured README body. LLM fills this; render_milo_readme is deterministic.

    # Ref: Milo design — Exploratory Summarizer, not Gatekeeper
    """

    who: str = Field(default="", description="2-4 sentence candidate story")
    career_context: str = Field(
        default="",
        description="Complex employment, user intent, constraints from chat",
    )
    transferable_skills: list[str] = Field(default_factory=list)
    target_industries: list[str] = Field(default_factory=list)
    role_archetypes: list[str] = Field(default_factory=list)
    deal_breakers: list[str] = Field(default_factory=list)
    guidance_for_agents: str = Field(
        default="",
        description="What Rex/Dana/Leo/Clara should remember (broaden, don't over-filter)",
    )

    @model_validator(mode="after")
    def strip_fields(self) -> "MiloReadmeDraft":
        self.who = self.who.strip()
        self.career_context = self.career_context.strip()
        self.guidance_for_agents = self.guidance_for_agents.strip()
        self.transferable_skills = [s.strip() for s in self.transferable_skills if s and s.strip()]
        self.target_industries = [s.strip() for s in self.target_industries if s and s.strip()]
        self.role_archetypes = [s.strip() for s in self.role_archetypes if s and s.strip()]
        self.deal_breakers = [s.strip() for s in self.deal_breakers if s and s.strip()]
        return self


def now_hk_iso() -> str:
    """Current Asia/Hong_Kong timestamp (ISO 8601, second precision).

    # Ref: workspace rule — Asia/Hong_Kong UTC+8
    """
    return datetime.now(HK_TZ).isoformat(timespec="seconds")


def milo_readme_path_for(profile_path: Path) -> Path:
    """Resolve the Milo README next to a candidate profile JSON.

    # Ref: config/master_profile.json → config/milo_context.md
    """
    path = Path(profile_path)
    if path.name == "master_profile.json":
        return path.parent / "milo_context.md"
    return path.with_name(f"{path.stem}_milo.md")


def live_chat_messages(chat_history: list) -> list[dict]:
    """Drop system/compression rows so batch size matches real turns.

    # Ref: milo_chat_history role = user | assistant | system
    """
    return [
        m for m in chat_history
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    ]


def should_refresh_readme(live_message_count: int) -> bool:
    """Refresh README for every live message in the first batch, then every 20.

    The first 20 user+assistant turns must still update the summary file.
    After that, rewrite on 40, 60, … so later history is batched.

    # Ref: user requirement — first 20 conversations still update the README
    """
    if live_message_count <= 0:
        return False
    if live_message_count <= CHAT_README_BATCH:
        return True
    return live_message_count % CHAT_README_BATCH == 0


def last_compress_path_for(profile_path: Path) -> Path:
    """Sibling file storing the last compressed chat excerpt.

    # Ref: config/master_profile.json → config/milo_last_compress.md
    """
    path = Path(profile_path)
    if path.name == "master_profile.json":
        return path.parent / "milo_last_compress.md"
    return path.with_name(f"{path.stem}_milo_last_compress.md")


def last_compressed_count(profile: dict) -> int:
    """Live-message watermark from the last successful compress.

    # Ref: master_profile.json milo_compress_state
    """
    state = profile.get("milo_compress_state") if isinstance(profile, dict) else None
    if not isinstance(state, dict):
        return -1
    try:
        return int(state.get("live_message_count", -1))
    except (TypeError, ValueError):
        return -1


def has_new_chat_since_compress(profile: dict, live_message_count: int) -> bool:
    """True when chat grew since the last saved compress record.

    # Ref: Rex/Milo skip re-compress when there is no new chat
    """
    last = last_compressed_count(profile)
    if last < 0:
        return True
    return live_message_count != last


def write_last_compress_record(
    profile_path: Path,
    *,
    live_message_count: int,
    narrative: str,
    chat_excerpt: str,
    compressed_at: str,
) -> Path:
    """Persist the last compressed chat so later Rex runs can skip if unchanged."""
    path = last_compress_path_for(profile_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"---\n"
        f"live_message_count: {live_message_count}\n"
        f"compressed_at: {compressed_at}\n"
        f"---\n\n"
        f"# Last Milo chat compress\n\n"
        f"## Executive narrative\n\n{narrative or '(none)'}\n\n"
        f"## Chat excerpt used\n\n```\n{chat_excerpt[:4000]}\n```\n"
    )
    path.write_text(body, encoding="utf-8")
    return path


def parse_readme_revision(text: str) -> int:
    """Read revision from YAML-like front matter. 0 if missing.

    # Ref: deterministic metadata, not LLM
    """
    match = _REVISION_RE.search(text or "")
    if not match:
        return 0
    return int(match.group(1))


def load_milo_readme(profile_path: Path) -> str:
    """Load the shared Milo README, or empty string if it does not exist."""
    path = milo_readme_path_for(profile_path)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def redact_pii_for_search(text: str) -> str:
    """Strip emails/phones before Rex horizon expansion (anonymized search).

    # Ref: talent_scout_agent_2 anonymized profile — no PII in Tavily/LLM search
    """
    cleaned = _EMAIL_RE.sub("[email]", text)
    return _PHONE_RE.sub("[phone]", cleaned)


def milo_readme_prompt_block(profile_path: Path, max_chars: int = 4000, *, redact: bool = False) -> str:
    """Prompt suffix other agents append. Empty if no README yet."""
    text = load_milo_readme(profile_path).strip()
    if not text:
        return ""
    if redact:
        text = redact_pii_for_search(text)
    clipped = text[:max_chars]
    return (
        "\n\nMILO CANDIDATE CONTEXT README "
        "(compressed CV + chat; soft guidance — broaden, do not hard-filter):\n"
        f"{clipped}"
    )


def fallback_draft(
    profile: dict,
    chat_excerpt: str = "",
    previous_readme: str = "",
) -> MiloReadmeDraft:
    """Deterministic draft when Ollama is unavailable.

    # Ref: workspace rule — thresholds/state as pure functions, no LLM guessing
    """
    basics = profile.get("basics") or {}
    pac = profile.get("acceptance_context") or {}
    skills: list[str] = []
    tech = profile.get("technical_skills") or {}
    if isinstance(tech, dict):
        for values in tech.values():
            if isinstance(values, list):
                skills.extend(str(v) for v in values)
    pac_skills = pac.get("core_transferable_skills") or []
    if isinstance(pac_skills, list):
        skills = list(dict.fromkeys([*pac_skills, *skills]))
    name = str(basics.get("name") or "Candidate")
    roles = basics.get("target_roles") or []
    role_line = ", ".join(str(r) for r in roles[:6]) if isinstance(roles, list) else ""
    who = str(pac.get("executive_narrative") or "").strip()
    if not who:
        who = f"{name} — {role_line}." if role_line else f"{name} profile loaded from CV."
    context = chat_excerpt.strip()[:800]
    if not context:
        context = "No extra chat notes yet. Ground this README in the CV and PAC only."
    return MiloReadmeDraft(
        who=who,
        career_context=context or str(pac.get("executive_narrative") or "No chat notes yet."),
        transferable_skills=skills[:16],
        target_industries=list(pac.get("target_industries") or [])[:12],
        role_archetypes=list(pac.get("role_archetypes") or (roles if isinstance(roles, list) else []))[:12],
        deal_breakers=list(pac.get("absolute_deal_breakers") or [])[:8],
        guidance_for_agents=(
            "Use this README to broaden search and tailor CVs. "
            "Only absolute deal-breakers are hard constraints."
        ),
    )


def render_milo_readme(
    draft: MiloReadmeDraft,
    *,
    updated_at: str,
    live_message_count: int,
    revision: int,
    source: str,
) -> str:
    """Render a skill-like Markdown README. Pure function.

    # Ref: Cursor SKILL.md shape — short front matter + sections other agents scan
    """

    def bullets(items: list[str]) -> str:
        if not items:
            return "- (none yet)"
        return "\n".join(f"- {item}" for item in items)

    return (
        f"---\n"
        f"name: milo-candidate-context\n"
        f"updated_at: {updated_at}\n"
        f"chat_messages: {live_message_count}\n"
        f"revision: {revision}\n"
        f"source: {source}\n"
        f"---\n\n"
        f"# Milo candidate context\n\n"
        f"Downstream agents (Rex, Dana, Leo, Clara) MUST read this file as the "
        f"compressed picture of the candidate. It is **soft guidance** — expand "
        f"search and tailoring; do not invent extra hard filters.\n\n"
        f"## Who\n\n{draft.who or '(pending)'}\n\n"
        f"## Career context (from CV + chat)\n\n{draft.career_context or '(pending)'}\n\n"
        f"## Transferable skills\n\n{bullets(draft.transferable_skills)}\n\n"
        f"## Target industries\n\n{bullets(draft.target_industries)}\n\n"
        f"## Role archetypes\n\n{bullets(draft.role_archetypes)}\n\n"
        f"## Absolute deal-breakers\n\n{bullets(draft.deal_breakers)}\n\n"
        f"## Guidance for other agents\n\n"
        f"{draft.guidance_for_agents or 'Broaden. Do not over-filter.'}\n"
    )


def write_milo_readme(profile_path: Path, markdown: str) -> Path:
    """Persist README next to the profile JSON."""
    path = milo_readme_path_for(profile_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = markdown if len(markdown) <= README_MAX_CHARS else markdown[:README_MAX_CHARS] + "\n"
    path.write_text(body, encoding="utf-8")
    return path
