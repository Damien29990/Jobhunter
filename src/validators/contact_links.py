"""Build clickable GitHub / LinkedIn / website URLs from profile handles.

# Ref: Leo Typst CV header — username-only input must still produce a PDF hyperlink
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

TYPST_SPECIAL = ("#", "$", "*", "_", "<", ">", "@", "\\", "[", "]")

_GITHUB_HOST = re.compile(r"(?:^|https?://)?(?:www\.)?github\.com/([^/?#]+)", re.I)
_SCHEME = re.compile(r"^https?://", re.I)
_LNKD_SHORT = re.compile(
    r"(?:^|https?://)?(?:www\.)?lnkd\.in/([A-Za-z0-9_-]{4,24})",
    re.I,
)
_MEMBER_ID = re.compile(r"^ACoAA[A-Za-z0-9_-]{8,120}$")
_LINKEDIN_SLUG = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{1,98}[A-Za-z0-9])?$")
_LINKEDIN_RESERVED = frozenset(
    {
        "in", "pub", "company", "school", "jobs", "feed", "login", "signup",
        "mwlite", "overlay", "details", "edit", "sales", "recruiter", "talent",
    }
)
_PATH_SUFFIXES = frozenset(
    {
        "overlay", "details", "recent-activity", "edit", "about-this-profile",
        "en", "fr", "de", "es", "it", "pt", "nl", "ja", "ko", "ru", "tr", "pl",
        "sv", "da", "fi", "no", "cs", "ro", "hu", "th", "vi", "id", "ms", "ar",
        "he", "zh", "zh-cn", "zh-tw", "zh-hk", "zh-hant", "zh-hans",
    }
)
_PLACEHOLDER_NAMES = frozenset({"your name", "name", "candidate", "untitled"})


@dataclass(frozen=True)
class LinkedInProfileRef:
    """Public profile pointer after LinkedIn 2026 share-link changes.

    # Ref: /in/{slug}, /in/?profileId=ACoAA…, /in/ACoAA…, lnkd.in/{code}
    """

    handle: str
    url: str
    profile_id: str = ""
    kind: str = "vanity"


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


def _query_member_id(query: str) -> str:
    params = parse_qs(query or "", keep_blank_values=False)
    for key in ("profileId", "miniProfileId", "memberId"):
        values = params.get(key) or []
        if values and values[0].strip():
            return unquote(values[0].strip())
    for key in ("miniProfileUrn", "profileUrn", "urn"):
        values = params.get(key) or []
        if not values:
            continue
        urn = unquote(values[0].strip())
        if ":" in urn:
            return urn.rsplit(":", 1)[-1]
    return ""


def _path_profile_slug(path: str) -> str:
    parts = [p for p in unquote(path or "").strip("/").split("/") if p]
    lowered = [p.lower() for p in parts]
    for marker in ("in", "pub"):
        if marker not in lowered:
            continue
        idx = lowered.index(marker)
        rest = parts[idx + 1 :]
        for segment in rest:
            if segment.lower() in _PATH_SUFFIXES:
                continue
            if segment.lower() in _LINKEDIN_RESERVED:
                return ""
            return segment
    if len(parts) >= 2 and parts[0].lower() == "mwlite" and parts[1].lower() == "in":
        rest = parts[2:]
        for segment in rest:
            if segment.lower() not in _PATH_SUFFIXES:
                return segment
    return ""


def parse_linkedin_profile_ref(raw: Optional[str]) -> Optional[LinkedInProfileRef]:
    """Accept 2026 share links, member ids, short links, and classic /in/{slug}."""
    text = (raw or "").strip()
    if not text or any(ch.isspace() for ch in text):
        return None
    text = text.lstrip("@")
    lower = text.lower()
    blocked = (
        "/company/",
        "/school/",
        "/jobs/",
        "/sales/",
        "/recruiter/",
        "linkedin.com/company",
        "linkedin.com/school",
        "linkedin.com/jobs",
        "linkedin.com/sales",
        "linkedin.com/recruiter",
    )
    if any(token in lower for token in blocked):
        return None

    short = _LNKD_SHORT.search(text)
    if short:
        code = short.group(1)
        return LinkedInProfileRef(
            handle=code,
            url=f"https://lnkd.in/{code}",
            kind="shortlink",
        )

    parsed = urlparse(text if "://" in text else f"https://{text}")
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    member_from_query = _query_member_id(parsed.query)
    slug = ""
    if "linkedin.com" in host or host.endswith("linkedin.com"):
        slug = _path_profile_slug(parsed.path)
    elif re.match(r"^in/", text, re.I):
        slug = _path_profile_slug("/" + text.split("?", 1)[0])
    elif "linkedin.com" not in lower and "/" not in text.split("?")[0]:
        slug = text.split("?")[0].strip("/")

    token = slug or member_from_query
    if not token:
        return None
    if token.lower() in _LINKEDIN_RESERVED:
        return None

    if _MEMBER_ID.match(token):
        url = f"https://www.linkedin.com/in/{token}"
        if not slug and member_from_query:
            url = f"https://www.linkedin.com/in/?profileId={token}"
        return LinkedInProfileRef(
            handle=token,
            url=url,
            profile_id=token,
            kind="member_id" if slug else "profile_id",
        )
    if not _LINKEDIN_SLUG.match(token):
        return None
    if len(token) < 3 or len(token) > 100:
        return None
    return LinkedInProfileRef(
        handle=token,
        url=f"https://www.linkedin.com/in/{token}",
        profile_id=member_from_query if _MEMBER_ID.match(member_from_query) else "",
        kind="vanity",
    )


def linkedin_profile_url(raw: Optional[str]) -> str:
    """Return a clickable LinkedIn profile URL from a slug, member id, or share link."""
    ref = parse_linkedin_profile_ref(raw)
    return ref.url if ref else ""


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
    ref = parse_linkedin_profile_ref(raw)
    return ref.handle if ref else ""


def is_valid_linkedin_username(raw: Optional[str]) -> bool:
    """True for a public profile slug, ACoAA member id, profileId share link, or lnkd.in.

    # Ref: LinkedIn 2026 mobile share uses /in/?profileId=ACoAA…
    """
    return parse_linkedin_profile_ref(raw) is not None


def name_from_linkedin_handle(handle: str) -> str:
    """Best-effort display name from a vanity slug (damien-yu → Damien Yu)."""
    slug = (handle or "").strip().strip("-")
    if not slug or _MEMBER_ID.match(slug) or slug.lower().startswith("lnkd"):
        return "Your Name"
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
