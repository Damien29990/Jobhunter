"""Seed a basic master profile from a public LinkedIn vanity username.

Does not log into LinkedIn. Uses Tavily public search/extract when a key is
set; otherwise writes a skeleton (name from slug + LinkedIn URL) so Milo CV
import can fill the rest.

# Ref: Milo intake — username-only bootstrap, CV merge still wins on full lists
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

_VALIDATORS_DIR = Path(__file__).resolve().parent.parent / "validators"
if str(_VALIDATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS_DIR))

from contact_links import (  # noqa: E402
    is_placeholder_profile_name,
    is_valid_linkedin_username,
    linkedin_handle,
    linkedin_profile_url,
    name_from_linkedin_handle,
)
from env_keys import tavily_api_key  # noqa: E402

AUTH_WALL_MARKERS = (
    "join linkedin",
    "sign in",
    "agree & join",
    "authwall",
    "linkedin is hiring",
)


class LinkedInBootstrapResult(BaseModel):
    """Outcome of a username bootstrap before it is merged into profile JSON.

    # Ref: POST /api/candidates/import-linkedin
    """

    handle: str
    url: str
    source: Literal["parsed", "skeleton"]
    parsed: dict = Field(default_factory=dict)
    public_text_chars: int = 0


def skeleton_profile(handle: str, url: str) -> dict:
    """Minimal profile when the public page is behind an auth wall.

    # Ref: config/master_profile.example.json basics
    """
    name = name_from_linkedin_handle(handle)
    return {
        "basics": {
            "name": name,
            "location": "Hong Kong",
            "email": "",
            "phone": "",
            "address": "",
            "website": "",
            "github": "",
            "linkedin": handle,
            "target_roles": [],
            "languages": [],
        },
        "education": [],
        "technical_skills": {},
        "experience": [],
        "projects": [],
        "certifications": [],
        "languages": [],
        "awards": [],
    }


def _looks_like_auth_wall(text: str) -> bool:
    sample = (text or "").strip().lower()[:800]
    if len(sample) < 40:
        return True
    return any(marker in sample for marker in AUTH_WALL_MARKERS) and len(sample) < 1200


def fetch_linkedin_public_text(url: str, handle: str) -> str:
    """Collect public snippets via Tavily. Empty when the key is missing.

    # Ref: Tavily Search/Extract — same key as Rex; no LinkedIn login
    """
    key = tavily_api_key()
    if not key:
        return ""
    try:
        from tavily import TavilyClient
    except ImportError:
        return ""
    client = TavilyClient(api_key=key)
    chunks: list[str] = []
    try:
        extracted = client.extract(urls=[url])
        for row in (extracted or {}).get("results") or []:
            if not isinstance(row, dict):
                continue
            text = str(row.get("raw_content") or row.get("content") or "").strip()
            if text and not _looks_like_auth_wall(text):
                chunks.append(text)
    except Exception:
        pass
    try:
        found = client.search(
            query=f'site:linkedin.com/in/{handle}',
            max_results=5,
            include_domains=["linkedin.com"],
        )
        for item in (found or {}).get("results") or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            content = str(item.get("content") or "").strip()
            blob = f"{title}\n{content}".strip()
            if blob and not _looks_like_auth_wall(blob):
                chunks.append(blob)
    except Exception:
        pass
    merged = "\n\n".join(chunks).strip()
    return merged[:12000]


def parse_linkedin_public_text(text: str, handle: str, url: str) -> Optional[dict]:
    """Reuse Milo's CV parser on public profile text."""
    if len((text or "").strip()) < 80:
        return None
    from milo_intake import import_cv

    parsed = import_cv(
        "PUBLIC LINKEDIN PROFILE TEXT (may be incomplete; do not invent):\n"
        f"Canonical URL: {url}\n"
        f"Vanity username: {handle}\n\n"
        f"{text.strip()}"
    )
    if not parsed or not isinstance(parsed, dict):
        return None
    basics = parsed.setdefault("basics", {})
    if not isinstance(basics, dict):
        parsed["basics"] = {"linkedin": handle, "name": name_from_linkedin_handle(handle)}
        return parsed
    basics["linkedin"] = handle
    if is_placeholder_profile_name(str(basics.get("name") or "")):
        basics["name"] = name_from_linkedin_handle(handle)
    if not str(basics.get("location") or "").strip():
        basics["location"] = "Hong Kong"
    return parsed


def bootstrap_from_linkedin(raw: str) -> LinkedInBootstrapResult:
    """Validate handle, fetch public text, parse or fall back to skeleton."""
    if not is_valid_linkedin_username(raw):
        raise ValueError("Enter a valid LinkedIn username or https://www.linkedin.com/in/… URL")
    handle = linkedin_handle(raw)
    url = linkedin_profile_url(raw)
    text = fetch_linkedin_public_text(url, handle)
    parsed = parse_linkedin_public_text(text, handle, url) if text else None
    if parsed:
        return LinkedInBootstrapResult(
            handle=handle,
            url=url,
            source="parsed",
            parsed=parsed,
            public_text_chars=len(text),
        )
    return LinkedInBootstrapResult(
        handle=handle,
        url=url,
        source="skeleton",
        parsed=skeleton_profile(handle, url),
        public_text_chars=len(text),
    )


def _is_empty_profile_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


def merge_fill_empty(existing: dict, parsed: dict) -> dict:
    """Write LinkedIn fields only where the profile is still empty.

    CV import uses replace-lists; this keeps a later Milo CV upload in charge.
    # Ref: _merge_parsed_profile fill_empty
    """
    out = dict(existing or {})
    incoming_basics = parsed.get("basics") if isinstance(parsed.get("basics"), dict) else {}
    basics = dict(out.get("basics") or {})
    for key, value in incoming_basics.items():
        if _is_empty_profile_value(value):
            continue
        if key == "linkedin":
            basics[key] = value
            continue
        if key == "name":
            if is_placeholder_profile_name(str(basics.get("name") or "")):
                basics[key] = value
            continue
        current = basics.get(key)
        if key in ("target_roles", "languages") and isinstance(value, list):
            if not isinstance(current, list) or not current:
                basics[key] = value
            else:
                seen = {str(item).strip().lower() for item in current}
                merged = list(current)
                for item in value:
                    label = str(item).strip()
                    if label and label.lower() not in seen:
                        merged.append(item)
                        seen.add(label.lower())
                basics[key] = merged
            continue
        if _is_empty_profile_value(current):
            basics[key] = value
    out["basics"] = basics
    for key in (
        "education",
        "experience",
        "projects",
        "certifications",
        "languages",
        "awards",
    ):
        incoming = parsed.get(key)
        if incoming and _is_empty_profile_value(out.get(key)):
            out[key] = incoming
    skills = parsed.get("technical_skills")
    if isinstance(skills, dict) and skills:
        existing_skills = dict(out.get("technical_skills") or {})
        for cat, tags in skills.items():
            if cat not in existing_skills or _is_empty_profile_value(existing_skills.get(cat)):
                existing_skills[cat] = tags
        out["technical_skills"] = existing_skills
    return out
