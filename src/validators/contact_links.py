"""Build clickable GitHub / LinkedIn / website URLs from profile handles.

# Ref: Leo Typst CV header — username-only input must still produce a PDF hyperlink
"""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

TYPST_SPECIAL = ("#", "$", "*", "_", "<", ">", "@", "\\", "[", "]")

_GITHUB_HOST = re.compile(r"(?:^|https?://)?(?:www\.)?github\.com/([^/?#]+)", re.I)
_LINKEDIN_IN = re.compile(
    r"(?:^|https?://)?(?:[a-z]{2}\.)?(?:www\.)?linkedin\.com/(?:in|pub|mwlite/in)/([^/?#]+)",
    re.I,
)
_SCHEME = re.compile(r"^https?://", re.I)


def _strip_handle(value: str) -> str:
    text = (value or "").strip()
    text = text.split("?")[0].split("#")[0].strip()
    return text.rstrip("/")


def github_profile_url(raw: Optional[str]) -> str:
    """Return https://github.com/{user} from a URL, github.com path, or username."""
    text = _strip_handle(raw or "")
    if not text:
        return ""
    text = text.lstrip("@")
    match = _GITHUB_HOST.search(text)
    if match:
        user = match.group(1).strip("/")
        return f"https://github.com/{user}" if user else ""
    if _SCHEME.search(text):
        path = urlparse(text).path.strip("/")
        user = path.split("/")[0] if path else ""
        return f"https://github.com/{user}" if user else ""
    user = text.split("/")[-1].strip()
    if not user:
        return ""
    return f"https://github.com/{user}"


def linkedin_profile_url(raw: Optional[str]) -> str:
    """Return https://www.linkedin.com/in/{slug} from a URL, /in/ path, or username."""
    text = _strip_handle(raw or "")
    if not text:
        return ""
    text = text.lstrip("@")
    match = _LINKEDIN_IN.search(text)
    if match:
        slug = match.group(1).strip("/")
        return f"https://www.linkedin.com/in/{slug}" if slug else ""
    if re.match(r"^in/", text, re.I):
        slug = text.split("/", 1)[1].strip("/")
        return f"https://www.linkedin.com/in/{slug}" if slug else ""
    if _SCHEME.search(text) and "linkedin.com" in text.lower():
        path = urlparse(text).path.strip("/")
        parts = [p for p in path.split("/") if p]
        if "in" in parts:
            idx = parts.index("in")
            if idx + 1 < len(parts):
                return f"https://www.linkedin.com/in/{parts[idx + 1]}"
        if parts:
            return f"https://www.linkedin.com/in/{parts[-1]}"
        return ""
    slug = text.split("/")[-1].strip()
    if not slug:
        return ""
    return f"https://www.linkedin.com/in/{slug}"


def website_url(raw: Optional[str]) -> str:
    """Return an https URL for a personal site; add a scheme when the user omitted it."""
    text = (raw or "").strip()
    if not text:
        return ""
    if _SCHEME.search(text):
        return text
    return f"https://{text.lstrip('/')}"


def github_handle(raw: Optional[str]) -> str:
    url = github_profile_url(raw)
    if not url:
        return ""
    return url.rstrip("/").rsplit("/", 1)[-1]


def linkedin_handle(raw: Optional[str]) -> str:
    url = linkedin_profile_url(raw)
    if not url:
        return ""
    return url.rstrip("/").rsplit("/", 1)[-1]


# LinkedIn vanity URLs are 3–100 characters: letters, digits, hyphen.
# Ref: LinkedIn public /in/{slug} — not company or job URLs
_LINKEDIN_SLUG = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{1,98}[A-Za-z0-9])?$")
_LINKEDIN_RESERVED = frozenset(
    {"in", "pub", "company", "school", "jobs", "feed", "login", "signup", "mwlite"}
)
_PLACEHOLDER_NAMES = frozenset({"your name", "name", "candidate", "untitled"})


def is_valid_linkedin_username(raw: Optional[str]) -> bool:
    """True when the value is a public /in/ vanity slug (or URL to one).

    # Ref: Milo LinkedIn bootstrap — reject company pages and junk slugs
    """
    text = (raw or "").strip()
    if not text or any(ch.isspace() for ch in text):
        return False
    lower = text.lower()
    blocked = (
        "/company/",
        "/school/",
        "/jobs/",
        "linkedin.com/company",
        "linkedin.com/school",
        "linkedin.com/jobs",
    )
    if any(token in lower for token in blocked):
        return False
    handle = linkedin_handle(text)
    if not handle or handle.lower() in _LINKEDIN_RESERVED:
        return False
    if len(handle) < 3 or len(handle) > 100:
        return False
    return bool(_LINKEDIN_SLUG.match(handle))


def name_from_linkedin_handle(handle: str) -> str:
    """Best-effort display name from a vanity slug (damien-yu → Damien Yu)."""
    slug = (handle or "").strip().strip("-")
    parts = [p for p in re.split(r"[-_]+", slug) if p and not p.isdigit()]
    if not parts:
        return slug.replace("-", " ").title() or "Your Name"
    return " ".join(p[:1].upper() + p[1:] for p in parts)


def is_placeholder_profile_name(name: Optional[str]) -> bool:
    text = (name or "").strip().lower()
    return (not text) or text in _PLACEHOLDER_NAMES


def website_label(raw: Optional[str]) -> str:
    url = website_url(raw)
    if not url:
        return ""
    host = urlparse(url).netloc or url
    host = re.sub(r"^www\.", "", host, flags=re.I)
    path = urlparse(url).path.rstrip("/")
    return f"{host}{path}" if path else host


def typ_escape(text: object) -> str:
    if text is None:
        return ""
    out: list[str] = []
    for ch in str(text):
        if ch in TYPST_SPECIAL:
            out.append("\\" + ch)
        else:
            out.append(ch)
    return "".join(out)


def typst_link(url: str, label: str) -> str:
    """Typst `#link("url")[label]` with a string-safe URL and escaped label."""
    safe_url = (url or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'#link("{safe_url}")[{typ_escape(label)}]'


def contact_typst_markup(basics: dict) -> str:
    """Header line for CV / cover letter: plain contact plus clickable profile links."""
    email = str(basics.get("email") or "").strip()
    phone = str(basics.get("phone") or "").strip()
    address = str(basics.get("address") or "").strip()
    location = str(basics.get("location") or "").strip()
    parts: list[str] = []
    if email:
        parts.append(typst_link(f"mailto:{email}", email))
    if phone:
        parts.append(typ_escape(phone))
    if address:
        parts.append(typ_escape(address))
        if location and location.lower() not in address.lower():
            parts.append(typ_escape(location))
    elif location:
        parts.append(typ_escape(location))

    gh = github_profile_url(str(basics.get("github") or ""))
    li = linkedin_profile_url(str(basics.get("linkedin") or ""))
    web = website_url(str(basics.get("website") or ""))
    if web:
        parts.append(typst_link(web, website_label(str(basics.get("website") or ""))))
    if gh:
        handle = github_handle(str(basics.get("github") or ""))
        parts.append(typst_link(gh, f"GitHub/{handle}" if handle else "GitHub"))
    if li:
        handle = linkedin_handle(str(basics.get("linkedin") or ""))
        parts.append(typst_link(li, f"LinkedIn/{handle}" if handle else "LinkedIn"))
    return " · ".join(parts) if parts else typ_escape("Hong Kong")


def contact_plain_lines(basics: dict) -> list[str]:
    """Non-Typst contact lines for the Markdown cover letter."""
    rows: list[str] = []
    for key in ("email", "phone", "address", "location"):
        value = str(basics.get(key) or "").strip()
        if value and value not in rows:
            rows.append(value)
    web = website_url(str(basics.get("website") or ""))
    gh = github_profile_url(str(basics.get("github") or ""))
    li = linkedin_profile_url(str(basics.get("linkedin") or ""))
    for url in (web, gh, li):
        if url and url not in rows:
            rows.append(url)
    return rows
