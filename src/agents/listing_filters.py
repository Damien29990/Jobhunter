"""Deterministic job-listing URL/title filters (no LLM, no extra deps).

# Ref: trusted-source policy — paid employment vacancies only
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlparse, urlunparse

_ACADEMIC_PATH_RE = re.compile(
    r"phd|mphil|dphil|research[-_ ]?postgraduate|taught[-_ ]?postgraduate|"
    r"rpg|prospectus|admission|graduate-school|research-degree|"
    r"studentship|scholarship|research[-_ ]programme",
    re.I,
)
_JOB_TITLE_HINTS = (
    "engineer", "developer", "analyst", "architect", "scientist", "manager",
    "specialist", "consultant", "lead", "sre", "devops", "programmer",
    "officer", "associate", "intern", "工程師", "開發", "分析", "架構",
)
_JUNK_TITLE_TOKENS = (
    "jobs in", "job search", "all jobs", "search results", "career home",
    "vacancies list", "career opportunities", "latest jobs",
    "jobs at ", "job at ", "we are hiring", "talent hiring", "graduate hiring",
    "view all", "open positions", "open roles",
)

_TITLE_STOPWORDS = {
    "hong", "kong", "job", "jobs", "details", "hiring", "limited", "ltd",
    "the", "and", "for", "with", "role", "vacancy", "careers", "career",
}

_JOBSDB_POSTING_RE = re.compile(r"/job/\d{5,}", re.I)
_JOBSDB_JOB_ID_RE = re.compile(
    r"(?:https?://(?:www\.)?(?:hk\.)?jobsdb\.com)?/job/(\d{5,})",
    re.I,
)
_JOBSDB_CARD_RE = re.compile(
    r"\[([^\]]+)\]\((?:https?://(?:www\.)?(?:hk\.)?jobsdb\.com)?/job/(\d{5,})",
    re.I,
)
_CTGOODJOBS_POSTING_RE = re.compile(r"/job/\d{4,}")
# HKSTP Science Park Talent Pool: /job/{id}/{slug}
# Ref: https://talentjobseeker.hkstp.org/job/103419/AI-Engineer-Cloud-Infrastructure-
_HKSTP_POSTING_RE = re.compile(r"/job/(\d{4,})(?:/|$)", re.I)
_HKSTP_CARD_RE = re.compile(
    r"(?:https?://(?:www\.)?talentjobseeker\.hkstp\.org)?/job/(\d{4,})(?:/([A-Za-z0-9._%-]*))?",
    re.I,
)
_GREENHOUSE_POSTING_RE = re.compile(r"/jobs/\d{5,}")
_LEVER_POSTING_RE = re.compile(
    r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)
_LINKEDIN_POSTING_RE = re.compile(r"/jobs/view/.+\d{6,}")
_WORKDAY_REQ_RE = re.compile(r"/reqId/\d{4,}|/job/\d{5,}|req=\d{4,}")
_SMARTRECRUITERS_RE = re.compile(r"/[A-Za-z0-9_-]+/\d{6,}")
_AMAZON_JOBS_RE = re.compile(r"/jobs/\d{5,}")
_PHENOM_JOB_RE = re.compile(
    r"/job/(?P<slug>[^/]+)/(?P<id>\d{6,})/?$",
    re.I,
)
_PHENOM_LOCALE_RE = re.compile(r"/(en_US|en_GB|zh_HK|zh_TW|zh_CN)/job/", re.I)
_EMPLOYER_POSTING_RE = re.compile(
    r"/(job|jobs|position|positions|vacancy|vacancies|career-opportunity)/"
    r"(\d{3,}|[a-z0-9-]{8,})",
    re.I,
)
_SEARCH_QUERY_RE = re.compile(r"(?:^|[?&])(q|query|keyword|keywords|search)=", re.I)


def extract_host(url: str) -> str:
    """Return lowercase hostname without leading www."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path.split("/")[0]).lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def is_phenom_job_url(url: str) -> bool:
    """True for Phenom TXM vacancy URLs used by HKJC, PCCW/HKT, and similar.

    Pattern: /job/{location-and-title-slug}/{numericId}
    # Ref: careers.hkjc.com, job.pccw.com
    """
    path = unquote(urlparse(url if "://" in url else f"https://{url}").path or "")
    return bool(_PHENOM_JOB_RE.search(path))


def normalize_listing_url(url: str) -> str:
    """Make a stored posting URL openable in a browser.

    HKJC Phenom pages 400 without a locale prefix. Decode once so %2C is not
    double-encoded.
    # Ref: careers.hkjc.com nginx 400 on malformed job path
    """
    raw = (url or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    path = parsed.path or ""
    host = extract_host(raw)
    decoded = unquote(path)
    if is_phenom_job_url(raw) and "hkjc.com" in host and not _PHENOM_LOCALE_RE.search(decoded):
        path = re.sub(r"/job/", "/en_US/job/", path, count=1)
    return urlunparse(
        (
            parsed.scheme or "https",
            parsed.netloc,
            path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )


def is_academic_non_job_url(url: str) -> bool:
    """True for university research-degree / admissions pages, not paid vacancies."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = extract_host(url)
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()
    blob = f"{path}?{query}"
    academic_host = (
        host.endswith(".edu.hk")
        or host.endswith(".edu")
        or ".ac.uk" in host
        or host.endswith(".ac.uk")
    )
    jobs_subdomain = (
        host.startswith("jobs.") or host.startswith("career.") or host.startswith("careers.")
    )
    if _ACADEMIC_PATH_RE.search(blob):
        return True
    if academic_host and not jobs_subdomain:
        jobish = any(
            token in path
            for token in ("/job", "/jobs", "/career", "/hro", "/vacancy", "/recruit", "/employment")
        )
        if not jobish:
            return True
    return False


def is_academic_programme_title(title: str) -> bool:
    """True if the title is a degree / research programme, not a job."""
    text = (title or "").lower()
    return bool(
        re.search(
            r"\b(phd|mphil|dphil|research postgraduate|taught postgraduate|"
            r"research degree|studentship|rpg programme)\b",
            text,
        )
    )


def is_junk_job_title(title: str) -> bool:
    """True for board search-result titles, not a single vacancy name."""
    text = (title or "").strip().lower()
    if not text:
        return True
    return any(token in text for token in _JUNK_TITLE_TOKENS)


def looks_like_job_title(title: str) -> bool:
    """Heuristic: title names a role rather than a category page."""
    text = (title or "").strip()
    if len(text) < 4 or is_junk_job_title(text) or is_academic_programme_title(text):
        return False
    lowered = text.lower()
    return any(hint in lowered for hint in _JOB_TITLE_HINTS)


def _clean_board_title_suffix(title: str) -> str:
    cleaned = title.strip()
    for sep in (
        " | JobsDB", " | CTgoodjobs", " | LinkedIn", " - JobsDB", " | SEEK",
        " | The Hong Kong Jockey Club", " | hktservice", " | HKT", " | PCCW",
    ):
        if sep.lower() in cleaned.lower():
            cleaned = re.split(re.escape(sep), cleaned, flags=re.I)[0].strip()
    stripped_details = re.sub(r"\s*Job Details\s*$", "", cleaned, flags=re.I).strip()
    if stripped_details:
        cleaned = stripped_details
    return cleaned


def clean_listing_title(title: str) -> str:
    """Public wrapper for board suffix cleanup."""
    return _clean_board_title_suffix(title)


def display_listing_title(title: str, url: str = "") -> str:
    """Readable vacancy name: drop board suffixes, recover Phenom/JobsDB slugs.

    # Ref: Phenom pages titled 'Job Details | The Hong Kong Jockey Club'
    """
    cleaned = _clean_board_title_suffix(title or "")
    generic = not cleaned or cleaned.lower() in {"job details", "details"} or is_junk_job_title(cleaned)
    if generic and url:
        slug = title_from_job_url(url)
        if slug:
            return slug
    return cleaned or (title or "").strip()


def title_from_job_url(url: str) -> str:
    """Recover a role name from a JobsDB-style /job/{id}/{slug} path."""
    path = unquote(urlparse(url if "://" in url else f"https://{url}").path).strip("/")
    parts = [p for p in path.split("/") if p]
    slug = ""
    if "job" in parts:
        idx = parts.index("job")
        rest = parts[idx + 1 :]
        if len(rest) >= 2 and re.fullmatch(r"\d{6,}", rest[-1] or ""):
            slug = rest[-2]
        elif len(rest) >= 2 and re.fullmatch(r"\d{5,}", rest[0] or ""):
            slug = rest[1]
        elif rest and not rest[0].isdigit():
            slug = rest[0]
    elif parts:
        slug = parts[-1]
    slug = re.sub(r"[-_]+", " ", slug)
    slug = re.sub(r"\d{5,}", " ", slug).strip()
    if len(slug.split()) < 2:
        return ""
    return slug.title()


def listing_url_problem(url: str) -> str | None:
    """Why this URL is not a single vacancy page, or None if it looks like one.

    # Ref: Tavily often returns search/index pages instead of the JD
    """
    if not (url or "").strip():
        return "empty url"
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = extract_host(url)
    path = (parsed.path or "/").lower().rstrip("/") or "/"
    query = parsed.query or ""

    if is_academic_non_job_url(url):
        return "academic or programme page"
    if _SEARCH_QUERY_RE.search(query) or path.endswith("/search") or "/search/" in path + "/":
        if "jobdetail" not in path and "job-detail" not in path and "/job/" not in path:
            return "search results page, not a posting"
    if "cpjobs.com" in host and "/search" in path:
        return "cpjobs search page"
    if "recruit.com.hk" in host and "jobdetail" not in path.lower():
        return "recruit index, not JobDetail"
    if is_phenom_job_url(url):
        return None

    if "jobsdb.com" in host:
        return None if _JOBSDB_POSTING_RE.search(path) else "JobsDB search or category page"
    if "ctgoodjobs.hk" in host:
        return None if _CTGOODJOBS_POSTING_RE.search(path) else "CTgoodjobs non-posting URL"
    if "talentjobseeker.hkstp.org" in host:
        return None if _HKSTP_POSTING_RE.search(path) else "HKSTP Talent Pool index, not a posting"
    if "greenhouse.io" in host:
        return None if _GREENHOUSE_POSTING_RE.search(path) else "Greenhouse board index"
    if "lever.co" in host:
        return None if _LEVER_POSTING_RE.search(path) else "Lever board index"
    if "linkedin.com" in host:
        return None if _LINKEDIN_POSTING_RE.search(path) else "LinkedIn is not a /jobs/view posting"
    if "myworkdayjobs.com" in host or "workday" in host:
        return None if _WORKDAY_REQ_RE.search(path) else "Workday non-requisition URL"
    if "smartrecruiters.com" in host:
        return None if _SMARTRECRUITERS_RE.search(path) else "SmartRecruiters index"
    if "amazon.jobs" in host:
        return None if _AMAZON_JOBS_RE.search(path) else "amazon.jobs index"

    if _EMPLOYER_POSTING_RE.search(path):
        return None

    generic = {
        "/", "/careers", "/career", "/jobs", "/job", "/vacancies", "/opportunities",
        "/about", "/about-us", "/en", "/hk", "/hong-kong", "/en/careers", "/en/jobs",
    }
    if path in generic or path.endswith("/careers") or path.endswith("/jobs"):
        return "employer careers index, not a posting"

    # Short path with no job id / slug — do not store as a vacancy.
    segments = [p for p in path.split("/") if p]
    has_digit_id = bool(re.search(r"\d{4,}", path))
    if len(segments) <= 1 and not has_digit_id:
        return "too generic to be a job posting"
    if not has_digit_id and len(segments) < 3:
        return "no job id in URL"
    return None


def is_jobsdb_category_url(url: str) -> bool:
    """True for JobsDB keyword/SEO index pages, not a single vacancy.

    # Ref: Tavily ranks hk.jobsdb.com/*-jobs over /job/{id}
    """
    return listing_url_problem(url) == "JobsDB search or category page"


def jobsdb_postings_from_listing_text(
    text: str,
    limit: int = 8,
) -> list[dict[str, str]]:
    """Pull /job/{id} cards out of a JobsDB category page (markdown or HTML).

    Tavily Search almost never returns individual JobsDB vacancies because SEEK
    SEO category pages outrank them. Category extract/search snippets still
    contain relative /job/94769754 links.
    # Ref: Tavily extract of hk.jobsdb.com python-engineer-jobs
    """
    cap = max(1, int(limit))
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for name, job_id in _JOBSDB_CARD_RE.findall(text or ""):
        posting = f"https://hk.jobsdb.com/job/{job_id}"
        if posting in seen:
            continue
        seen.add(posting)
        found.append({"url": posting, "title": (name or "").strip()})
        if len(found) >= cap:
            return found
    for job_id in _JOBSDB_JOB_ID_RE.findall(text or ""):
        posting = f"https://hk.jobsdb.com/job/{job_id}"
        if posting in seen:
            continue
        seen.add(posting)
        found.append({"url": posting, "title": ""})
        if len(found) >= cap:
            break
    return found


def is_hkstp_listing_url(url: str) -> bool:
    """True for the HKSTP Talent Pool home/index, not a single vacancy.

    # Ref: https://talentjobseeker.hkstp.org/
    """
    return listing_url_problem(url) == "HKSTP Talent Pool index, not a posting"


def hkstp_postings_from_listing_text(
    text: str,
    limit: int = 8,
) -> list[dict[str, str]]:
    """Pull /job/{id}/{slug} cards out of the HKSTP Talent Pool index.

    # Ref: talentjobseeker.hkstp.org/job/103419/AI-Engineer-Cloud-Infrastructure-
    """
    cap = max(1, int(limit))
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for job_id, slug in _HKSTP_CARD_RE.findall(text or ""):
        slug = (slug or "").strip("/")
        posting = f"https://talentjobseeker.hkstp.org/job/{job_id}"
        if slug:
            posting = f"{posting}/{slug}"
        if posting in seen:
            continue
        seen.add(posting)
        title = re.sub(r"[-_]+", " ", slug).strip() if slug else ""
        found.append({"url": posting, "title": title})
        if len(found) >= cap:
            break
    return found


def is_job_posting_url(url: str) -> bool:
    """True only for an individual vacancy URL (not search/category/home)."""
    return listing_url_problem(url) is None


def listing_text_supports_title(page_text: str, title: str) -> bool:
    """True if enough distinctive title tokens appear in the page/snippet.

    # Ref: LLM often names a role that the source URL does not contain
    """
    tokens = [
        tok
        for tok in re.findall(r"[a-zA-Z\u4e00-\u9fff]{4,}", (title or "").lower())
        if tok not in _TITLE_STOPWORDS
    ]
    if len(tokens) < 2:
        return True
    blob = (page_text or "").lower()
    if not blob.strip():
        return True
    hits = sum(1 for tok in tokens if tok in blob)
    return hits >= max(2, (len(tokens) + 1) // 2)


def listing_check_verdict(
    url_problem: str | None,
    http_ok: bool | None,
    status_code: int | None,
    title_found: bool | None,
) -> tuple[bool, bool, str]:
    """Decide if a vacancy is still listed and whether to mark expired.

    Network/auth failures skip research but do not expire (unknown).
    Search pages, 404/410, and title-missing 200 pages expire.

    Returns (still_listed, should_expire, reason).
    # Ref: Dana pre-research listing check
    """
    if url_problem:
        return False, True, url_problem
    if http_ok is None:
        return False, False, "not fetched"
    if status_code in (404, 410):
        return False, True, f"HTTP {status_code}"
    if not http_ok:
        return False, False, f"HTTP {status_code or 'error'}"
    if title_found is False:
        return False, True, "page does not contain job title"
    return True, False, "ok"


def prefer_listing_title(tavily_title: str, url: str, llm_title: str) -> str:
    """Prefer the board/Tavily title or URL slug over a rewritten LLM title."""
    tav = _clean_board_title_suffix(tavily_title or "")
    llm = (llm_title or "").strip()
    slug = title_from_job_url(url)
    if looks_like_job_title(tav):
        return tav[:180]
    if looks_like_job_title(llm) and not is_junk_job_title(llm):
        return llm[:180]
    if slug:
        return slug[:180]
    return (llm or tav or "Untitled role")[:180]
