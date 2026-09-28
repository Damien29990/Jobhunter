"""Deterministic job-listing URL/title filters (no LLM, no extra deps).

# Ref: trusted-source policy — paid employment vacancies only
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

JD_FULL_MAX = 200_000


def clip_listing_text(text: str, limit: int = JD_FULL_MAX) -> str:
    """Cap stored full JD length.

    # Ref: job_postings.jd_full
    """
    raw = text or ""
    if len(raw) <= limit:
        return raw
    return raw[:limit]


def listing_full_text(job: dict) -> str:
    """Prefer jd_full, then the short snippet.

    # Ref: job_postings.jd_full vs jd_snippet
    """
    return str(job.get("jd_full") or job.get("jd_snippet") or "").strip()

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
_LINKEDIN_POSTING_RE = re.compile(r"/jobs/view/.+\d{6,}|/jobs/view/\d{6,}", re.I)
_LINKEDIN_JOB_ID_RE = re.compile(
    r"(?:[?&]currentJobId=|/jobs/view/(?:[^/?#]*-)?)(\d{6,})",
    re.I,
)
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
_TRACKING_QUERY_KEYS = frozenset(
    {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "mc_cid", "mc_eid", "type",
    }
)
_POSTED_ON_TEXT = re.compile(
    r"(?:posted(?:\s+on)?|date\s*posted|publish(?:ed)?(?:\s+on)?|發布日期|刊登日期|張貼日期)"
    r"\s*[:：]?\s*"
    r"(\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})",
    re.I,
)
_POSTED_AGO_TEXT = re.compile(
    r"posted\s+(\d+)\s*(d|day|days|h|hr|hrs|hour|hours)\s+ago",
    re.I,
)
_JSON_DATE_POSTED = re.compile(r'"datePosted"\s*:\s*"([^"]+)"', re.I)


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


def linkedin_job_id(url: str) -> str:
    """Numeric LinkedIn job id from /jobs/view/… or currentJobId= (2024–2026 share links).

    # Ref: linkedin.com/jobs/view/{slug}-{id} and ?currentJobId=
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    query_id = ""
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() == "currentjobid" and re.fullmatch(r"\d{6,}", value or ""):
            query_id = value
            break
    if query_id:
        return query_id
    path = parsed.path or ""
    match = re.search(r"/jobs/view/(?:[^/]*-)?(\d{6,})/?$", path, re.I)
    if match:
        return match.group(1)
    match = re.search(r"/jobs/view/(\d{6,})", path, re.I)
    return match.group(1) if match else ""


def normalize_listing_url(url: str) -> str:
    """Make a stored posting URL openable and unique across query/slug variants.

    HKJC Phenom pages 400 without a locale prefix. Decode once so %2C is not
    double-encoded. JobsDB / HKSTP keep /job/{id} so slug and tracking params
    do not create duplicate rows.
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
    jobsdb_id = re.search(r"/job/(\d{5,})", path, re.I)
    if "jobsdb.com" in host and jobsdb_id:
        path = f"/job/{jobsdb_id.group(1)}"
    hkstp_id = _HKSTP_POSTING_RE.search(path)
    if "talentjobseeker.hkstp.org" in host and hkstp_id:
        path = f"/job/{hkstp_id.group(1)}"
    ct_id = re.search(r"/job/(\d{4,})", path, re.I)
    if "ctgoodjobs.hk" in host and ct_id:
        path = f"/job/{ct_id.group(1)}"
    li_job = linkedin_job_id(raw)
    if "linkedin.com" in host and li_job:
        path = f"/jobs/view/{li_job}"
        netloc = "www.linkedin.com"
        return urlunparse(("https", netloc, path, "", "", ""))
    path = re.sub(r"/{2,}", "/", path)
    if len(path) > 1:
        path = path.rstrip("/")
    kept_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_KEYS
    ]
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    scheme = (parsed.scheme or "https").lower()
    return urlunparse(
        (
            scheme,
            netloc,
            path,
            parsed.params,
            urlencode(kept_query),
            "",
        )
    )


def parse_posted_at(*texts: str) -> str:
    """ISO Asia/Hong_Kong stamp from Tavily published_date or JD 'Posted on' text.

    # Ref: job_postings.posted_at — board publish time, not Rex created_at
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    hk = ZoneInfo("Asia/Hong_Kong")
    for text in texts:
        raw = str(text or "").strip()
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=hk)
            return parsed.astimezone(hk).isoformat()
        except ValueError:
            pass
        blob = raw.replace("\n", " ")
        json_match = _JSON_DATE_POSTED.search(blob)
        if json_match:
            nested = parse_posted_at(json_match.group(1))
            if nested:
                return nested
        match = _POSTED_ON_TEXT.search(blob)
        if match:
            stamp = match.group(1).replace("/", "-")
            for fmt in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    parsed = datetime.strptime(stamp, fmt).replace(tzinfo=hk)
                    return parsed.isoformat()
                except ValueError:
                    continue
        ago = _POSTED_AGO_TEXT.search(blob)
        if ago:
            amount = int(ago.group(1))
            unit = ago.group(2).lower()
            now = datetime.now(hk)
            if unit.startswith("h"):
                parsed = now - timedelta(hours=amount)
            else:
                parsed = now - timedelta(days=amount)
            return parsed.replace(microsecond=0).isoformat()
    return ""


def folded_listing_title(job_title: str) -> str:
    """Lowercase title with punctuation stripped for duplicate matching."""
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", (job_title or "").lower()).strip()


def listing_duplicate_key(company_name: str, job_title: str) -> tuple[str, str] | None:
    """Stable employer+title key used to collapse the same vacancy on two boards.

    # Ref: HKPC Researcher listed on JobsDB and a second careers URL
    """
    company = (company_name or "").strip().lower()
    title = folded_listing_title(job_title)
    if len(title) < 8:
        return None
    if company in {"", "undisclosed employer", "not disclosed"}:
        return None
    return (company, title)


def listing_titles_same_vacancy(left: str, right: str) -> bool:
    """True when two titles are the same role, allowing a one-letter board typo."""
    folded_left = folded_listing_title(left)
    folded_right = folded_listing_title(right)
    if not folded_left or not folded_right:
        return False
    if folded_left == folded_right:
        return True
    if min(len(folded_left), len(folded_right)) < 12:
        return False
    return SequenceMatcher(None, folded_left, folded_right).ratio() >= 0.92


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
    if linkedin_job_id(url):
        return None
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
        return None if linkedin_job_id(url) else "LinkedIn is not a /jobs/view posting"
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
