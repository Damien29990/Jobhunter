"""Deterministic Rex listing filters — paid jobs only, keep board titles.

# Ref: talent_scout_agent URL/title validators
"""

from __future__ import annotations

import sys
from pathlib import Path

_AGENTS = Path(__file__).resolve().parents[1] / "src" / "agents"
if str(_AGENTS) not in sys.path:
    sys.path.insert(0, str(_AGENTS))

from listing_filters import (
    is_academic_non_job_url,
    is_academic_programme_title,
    is_job_posting_url,
    is_jobsdb_category_url,
    is_hkstp_listing_url,
    is_junk_job_title,
    jobsdb_postings_from_listing_text,
    hkstp_postings_from_listing_text,
    listing_check_verdict,
    listing_text_supports_title,
    listing_url_problem,
    normalize_listing_url,
    prefer_listing_title,
    title_from_job_url,
    clean_listing_title,
    display_listing_title,
)


def test_reject_university_research_programme_pages() -> None:
    rpg = "https://www.polyu.edu.hk/gs/research-postgraduate-programmes/phd/"
    assert is_academic_non_job_url(rpg) is True
    campus = "https://www.cuhk.edu.hk/english/research/index.html"
    assert is_academic_non_job_url(campus) is True


def test_keep_university_jobs_subdomain() -> None:
    hku = "https://jobs.hku.hk/en_US/job/12345/software-engineer"
    assert is_academic_non_job_url(hku) is False


def test_reject_phd_titles() -> None:
    assert is_academic_programme_title("PhD in Electronic Engineering") is True
    assert is_academic_programme_title("Senior Software Engineer") is False


def test_prefer_tavily_title_over_paraphrase() -> None:
    url = "https://hk.jobsdb.com/job/80001234/building-services-engineer-hong-kong"
    chosen = prefer_listing_title(
        "Building Services Engineer | JobsDB",
        url,
        "Platform Engineer",
    )
    assert chosen == "Building Services Engineer"


def test_title_from_jobsdb_slug() -> None:
    url = "https://hk.jobsdb.com/job/80001234/senior-full-stack-engineer-python"
    assert "Full Stack" in title_from_job_url(url) or "Senior" in title_from_job_url(url)


def test_reject_search_and_index_urls() -> None:
    assert listing_url_problem("https://www.cpjobs.com/hk/en/search?q=Senior+Resident+Engineer")
    assert is_job_posting_url(
        "https://www.cpjobs.com/hk/en/search?q=inspector+of+works"
    ) is False
    assert is_job_posting_url("https://hk.jobsdb.com/bms-system-jobs") is False
    assert is_job_posting_url(
        "https://hk.jobsdb.com/job/80001234/building-services-engineer"
    ) is True
    assert is_job_posting_url(
        "https://hk.jobsdb.com/en/job/80001234/software-engineer"
    ) is True
    assert is_job_posting_url("https://hk.jobsdb.com/jobs-in-hong-kong") is False
    assert is_jobsdb_category_url("https://hk.jobsdb.com/python-engineer-jobs") is True
    cards = jobsdb_postings_from_listing_text(
        "### [Software Engineer](/job/94769754?type=standard)\n"
        "### [Data Engineer](https://hk.jobsdb.com/job/94467886)\n"
        "noise /python-jobs"
    )
    assert [item["url"] for item in cards] == [
        "https://hk.jobsdb.com/job/94769754",
        "https://hk.jobsdb.com/job/94467886",
    ]
    assert cards[0]["title"] == "Software Engineer"
    assert is_job_posting_url(
        "https://hk.linkedin.com/jobs/view/ai-full-stack-engineer-at-midas-analytics-4465495711"
    ) is True
    assert is_job_posting_url("https://job-boards.greenhouse.io/hyphenconnect") is False
    assert is_junk_job_title("Jobs at Hyphen Connect Limited") is True


def test_snippet_must_support_title() -> None:
    page = "We are hiring an Agentic Systems Architect in Hong Kong."
    assert listing_text_supports_title(page, "Agentic Systems Architect") is True
    assert listing_text_supports_title(
        "Search jobs in Hong Kong construction",
        "Senior Resident Engineer Building Services",
    ) is False


def test_listing_check_verdict_expire_rules() -> None:
    still, expire, _ = listing_check_verdict("search results page, not a job posting", None, None, None)
    assert still is False and expire is True
    still, expire, _ = listing_check_verdict(None, False, 404, None)
    assert still is False and expire is True
    still, expire, _ = listing_check_verdict(None, False, 410, None)
    assert still is False and expire is True
    still, expire, _ = listing_check_verdict(None, True, 200, False)
    assert still is False and expire is True
    still, expire, _ = listing_check_verdict(None, False, 403, None)
    assert still is False and expire is False
    still, expire, _ = listing_check_verdict(None, False, 503, None)
    assert still is False and expire is False
    still, expire, _ = listing_check_verdict(None, False, None, None)
    assert still is False and expire is False
    still, expire, reason = listing_check_verdict(None, True, 200, True)
    assert still is True and expire is False and reason == "ok"


def test_phenom_hkjc_hkt_are_job_postings() -> None:
    hkjc = (
        "https://careers.hkjc.com/job/"
        "hong-kong%2Csar-china-assistant-manager-application-development/1234567"
    )
    hkt = "https://job.pccw.com/job/hong-kong-software-engineer-hkt/2345678"
    assert is_job_posting_url(hkjc) is True
    assert is_job_posting_url(hkt) is True
    assert listing_url_problem(hkjc) is None
    assert listing_url_problem(hkt) is None
    normalized = normalize_listing_url(hkjc)
    assert "/en_US/job/" in normalized
    assert "%2C" in normalized
    assert normalize_listing_url(hkt) == hkt
    slug_title = title_from_job_url(hkjc)
    assert "Application Development" in slug_title or "Assistant Manager" in slug_title
    assert display_listing_title("Job Details | The Hong Kong Jockey Club", hkjc) == slug_title
    assert clean_listing_title("Software Engineer | HKT") == "Software Engineer"


def test_user_paste_allows_non_tavily_posting_but_rejects_search() -> None:
    """Pasted Rex URLs skip the Tavily domain whitelist; search pages still fail.

    # Ref: listing_url_problem / is_job_posting_url
    """
    posting = "https://careers.example-bank.com/jobs/12345/python-backend-engineer"
    search = "https://hk.jobsdb.com/python-jobs"
    assert listing_url_problem(posting) is None
    assert is_job_posting_url(posting) is True
    assert is_job_posting_url(search) is False
    assert listing_url_problem(search)


def test_hkstp_talent_pool_posting_vs_home() -> None:
    home = "https://talentjobseeker.hkstp.org/"
    posting = "https://talentjobseeker.hkstp.org/job/103419/AI-Engineer-Cloud-Infrastructure-"
    assert is_hkstp_listing_url(home) is True
    assert is_job_posting_url(home) is False
    assert is_job_posting_url(posting) is True
    cards = hkstp_postings_from_listing_text(
        "[AI Engineer](https://talentjobseeker.hkstp.org/job/103419/AI-Engineer-Cloud-Infrastructure-)\n"
        "/job/101786/Senior-Power-Electronics-R-D-Engineer"
    )
    urls = {c["url"] for c in cards}
    assert posting in urls
    assert "https://talentjobseeker.hkstp.org/job/101786/Senior-Power-Electronics-R-D-Engineer" in urls
