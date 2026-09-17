"""Due-diligence agent: background research on high-match employers."""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib.parse import quote, urljoin

import httpx
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from tavily import TavilyClient

AGENT_DIR = Path(__file__).resolve().parent
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from talent_scout_agent import (  # noqa: E402
    DEEPSEEK_BASE_URL,
    DEEPSEEK_CHAT_MODEL,
    PROJECT_ROOT,
    DEFAULT_PROFILE_PATH,
    JobDBManager,
    domains_for_companies,
    extract_host,
    is_usable_company_name,
    parse_json_payload,
    resolve_employer_name,
    fetch_page_text,
    passes_dana_composite_gate,
)

from listing_filters import (  # noqa: E402
    listing_check_verdict,
    listing_text_supports_title,
    listing_url_problem,
    normalize_listing_url,
)
from llm_usage import instrument_openai  # noqa: E402

from activity_logger import log_activity  # noqa: E402
from milo_context import milo_readme_prompt_block  # noqa: E402
from notify import notify_job_update  # noqa: E402

# Sentiment / news / tech hosts for Tavily lanes (keep each lane short).
# Ref: Tavily include_domains — short lists rank better
HK_NEWS_DOMAINS: List[str] = [
    "scmp.com",
    "reuters.com",
    "bloomberg.com",
    "hkexnews.hk",
    "thestandard.com.hk",
    "news.gov.hk",
]
SENTIMENT_DOMAINS: List[str] = [
    "glassdoor.com",
    "hk.jobsdb.com",
    "ctgoodjobs.hk",
    "teamblind.com",
    "levels.fyi",
]
TECH_FORUM_DOMAINS: List[str] = [
    "github.com",
    "medium.com",
    "infoq.com",
    "stackoverflow.com",
    "reddit.com",
]
HK_RESEARCH_DOMAINS: List[str] = HK_NEWS_DOMAINS + ["linkedin.com"]
SEARCH_CACHE_MAX_AGE_DAYS = 14
MIN_MATCH_SCORE = 80
DOSSIER_OUTPUT_DIR = PROJECT_ROOT / "output" / "dossiers"
MAX_RESEARCH_BLOB_CHARS = 16000
DOSSIER_JSON_EXAMPLE = {
    "company_name": "Example Ltd",
    "vetting_verdict": "PROCEED",
    "salary_benchmark": "Not disclosed in retrieved sources",
    "detected_tech_stack": ["SCADA", "IIoT"],
    "engineering_culture": "Short grounded summary.",
    "glassdoor_sentiment": "Sector inference if no reviews.",
    "recent_news_and_events": ["One sourced event."],
    "architectural_trade_offs": "Short grounded summary.",
    "red_flags": ["One sourced risk."],
    "green_flags": ["One sourced positive."],
    "reverse_interview_questions": ["Question 1?", "Question 2?", "Question 3?"],
    "source_urls": ["https://example.com"],
    "confidence": 55,
}
HTTP_USER_AGENT = (
    "JobhunterDueDiligence/0.1 (local employer-research agent; "
    "https://en.wikipedia.org/wiki/Wikipedia:WikiProject_Companies)"
)
OFFICIAL_ABOUT_PATHS = (
    "/",
    "/about",
    "/about-us",
    "/en/about",
    "/en/about-us",
    "/en/business-solution",
    "/business-solution",
    "/investors",
    "/our-company",
)

# Extra searchable names when the legal title is a composite bilingual string.
# Ref: ATAL ↔ Analogue Holdings / 安樂工程
KNOWN_GROUP_ALIASES: Dict[str, List[str]] = {
    "atal": [
        "Analogue Holdings",
        "安樂工程",
        "ATAL Engineering",
        "ATAL Building Services",
    ],
}


class CompanyDueDiligence(BaseModel):
    """Actionable employer dossier: news, sentiment, tech debt, interview brief.

    # Ref: Agent 2 deep-dossier contract
    """

    company_name: str
    vetting_verdict: str = Field(
        default="PROCEED",
        description="PROCEED (recommended to apply) or AVOID (high risks)",
    )
    salary_benchmark: str = Field(
        description="Estimated market compensation range (HKD) or Glassdoor data"
    )
    detected_tech_stack: List[str] = Field(
        description="Observed production technologies, tools, and platforms"
    )
    engineering_culture: str = Field(
        description="Delivery cadence, automation standards, and deployment practices"
    )
    glassdoor_sentiment: str = Field(
        description="Summary of employee reviews, pros/cons, management culture, and WLB"
    )
    recent_news_and_events: List[str] = Field(
        description="Key developments within the last 12-24 months (e.g. tenders, tech overhauls, layoffs)"
    )
    architectural_trade_offs: str = Field(
        description="Technical debt, legacy platforms, and modernization bets inferred from sources"
    )
    red_flags: List[str] = Field(
        description="Identified risks (e.g. legacy tech debt, high turnover, micromanagement)"
    )
    green_flags: List[str] = Field(
        description="Positive factors (e.g. cloud-native modernization, strong engineering ownership)"
    )
    reverse_interview_questions: List[str] = Field(
        description="3-5 senior-level architectural/organizational questions to ask the interviewer"
    )
    source_urls: List[str] = Field(
        default_factory=list, description="URLs actually used as evidence"
    )
    confidence: int = Field(
        default=50, ge=0, le=100, description="Evidence sufficiency 0-100"
    )


def load_master_profile(path: Path = DEFAULT_PROFILE_PATH) -> dict:
    """Load config/master_profile.json. Placeholder fields are fine until you fill real data."""
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def profile_brief(profile: dict) -> str:
    """Compact candidate context for the research LLM. Does not invent missing facts."""
    basics = profile.get("basics") or {}
    skills: List[str] = []
    for job in profile.get("experience") or []:
        skills.extend(job.get("skills_used") or [])
    for project in profile.get("projects") or []:
        skills.extend(project.get("tech_stack") or [])
    unique_skills = list(dict.fromkeys(skills))
    return json.dumps(
        {
            "location": basics.get("location"),
            "target_roles": basics.get("target_roles"),
            "min_expected_salary_hkd": basics.get("min_expected_salary_hkd"),
            "skills": unique_skills,
            "recent_roles": [
                {
                    "company": item.get("company"),
                    "role": item.get("role"),
                    "highlights": item.get("highlights"),
                }
                for item in (profile.get("experience") or [])
            ],
        },
        ensure_ascii=False,
    )


def research_cache_key(company_name: str, backend: str) -> str:
    normalized = " ".join(company_name.lower().split())
    digest = hashlib.sha256(f"dd_v5|{backend}|{normalized}".encode("utf-8")).hexdigest()
    return digest


def extract_company_aliases(full_name: str) -> List[str]:
    """Extract clean search tokens and language variants from formal company names."""
    aliases = [full_name.strip()]

    zh_match = re.search(r"[\(（](.*?)[\)）]", full_name)
    if zh_match:
        zh_clean = zh_match.group(1).strip()
        aliases.append(zh_clean)
        aliases.append(
            zh_clean.replace("有限公司", "").replace("工程", "").strip()
        )

    for cjk in re.findall(r"[\u4e00-\u9fff]{2,}", full_name):
        aliases.append(cjk)
        aliases.append(cjk.replace("有限公司", "").replace("工程", "").strip())

    clean_en = re.sub(r"[\(（].*?[\)）]", "", full_name)
    clean_en = re.sub(r"[\u4e00-\u9fff]+", " ", clean_en)
    clean_en = re.sub(
        r"\b(Ltd|Limited|Technologies|Technology|Engineering|Group|Holdings|Holding)\b\.?",
        "",
        clean_en,
        flags=re.IGNORECASE,
    ).strip(" ,.-")
    if clean_en:
        aliases.append(clean_en)
        first = clean_en.split()[0] if clean_en.split() else ""
        if len(first) >= 3:
            aliases.append(first)

    folded = full_name.lower()
    for key, extras in KNOWN_GROUP_ALIASES.items():
        if key in folded or any(key in a.lower() for a in aliases):
            aliases.extend(extras)

    cleaned = []
    skip = {"hk", "co", "the", "and", "hong", "kong", "ltd", "limited"}
    for alias in aliases:
        item = " ".join(alias.split())
        if len(item) >= 2 and item.lower() not in skip:
            cleaned.append(item)
    return list(dict.fromkeys(cleaned))


def primary_search_aliases(full_name: str, limit: int = 3) -> List[str]:
    """Short list of aliases used in Tavily queries (avoid exploding credit use)."""
    aliases = extract_company_aliases(full_name)
    ranked = sorted(aliases, key=lambda item: (len(item.split()), len(item)))
    # Prefer distinctive short English + one Chinese name.
    picked: List[str] = []
    for alias in ranked:
        if alias == full_name.strip() and len(aliases) > 1:
            continue
        picked.append(alias)
        if len(picked) >= limit:
            break
    if full_name.strip() not in picked:
        picked.append(full_name.strip())
    return list(dict.fromkeys(picked))[: limit + 1]


def safe_dossier_stem(company_name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "_", company_name)
    cleaned = " ".join(cleaned.split())
    return (cleaned[:80] or "company").rstrip(" .")


def normalize_verdict(value: str) -> str:
    upper = (value or "").upper()
    if "AVOID" in upper:
        return "AVOID"
    return "PROCEED"


def _cheap_json_repair(text: str) -> str:
    """Fix trailing commas and truncated outer braces before a full repair pass."""
    cleaned = text.strip().lstrip("\ufeff")
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    if cleaned.count("{") > cleaned.count("}"):
        cleaned += "}" * (cleaned.count("{") - cleaned.count("}"))
    if cleaned.count("[") > cleaned.count("]"):
        cleaned += "]" * (cleaned.count("[") - cleaned.count("]"))
    return cleaned


def loads_llm_json_object(raw: str) -> dict:
    """Parse DeepSeek JSON even when quotes/commas are slightly malformed.

    # Ref: LLM json_object is not guaranteed syntactically valid
    """
    text = parse_json_payload(raw)
    candidates = [text, _cheap_json_repair(text)]
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            obj = json.loads(candidate, strict=False)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError as exc:
            last_error = exc
    try:
        from json_repair import loads as json_repair_loads

        obj = json_repair_loads(text)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, str):
            obj = json.loads(obj, strict=False)
        if isinstance(obj, dict):
            return obj
    except Exception as exc:
        last_error = exc
    if last_error:
        raise last_error
    raise ValueError("dossier JSON is not an object")


def dump_parse_failure(company_name: str, raw: str, exc: Exception) -> Path:
    """Keep the broken LLM payload so a parse miss is inspectable."""
    folder = DOSSIER_OUTPUT_DIR / "_parse_failures"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{safe_dossier_stem(company_name)}_raw.txt"
    parsed = parse_json_payload(raw)
    pos = getattr(exc, "pos", None)
    around = ""
    if isinstance(pos, int):
        start = max(0, pos - 160)
        around = (
            f"\n\n--- around error pos {pos} (line {getattr(exc, 'lineno', '?')}) ---\n"
            f"{parsed[start : pos + 160]}\n"
        )
    path.write_text(
        f"{exc}{around}\n--- raw ---\n{raw}",
        encoding="utf-8",
    )
    return path


def compact_research_blob(search_hits: Sequence[dict], max_chars: int = MAX_RESEARCH_BLOB_CHARS) -> str:
    """Cap excerpt size so the LLM JSON stays small enough to remain valid."""
    parts: List[str] = []
    used = 0
    for item in list(search_hits)[:18]:
        snippet = _snippet(item)[:1200]
        block = f"URL: {item.get('url')}\nTITLE: {item.get('title')}\n{snippet}"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts) or "(no search hits)"


def coerce_dossier_payload(raw: str, company_name: str) -> dict:
    """Fill aliases/defaults so a missing vetting_verdict does not drop the whole report."""
    payload = loads_llm_json_object(raw)
    if not isinstance(payload, dict):
        raise ValueError("dossier JSON is not an object")
    verdict = payload.get("vetting_verdict") or payload.get("verdict") or payload.get("recommendation")
    if not verdict:
        verdict = "PROCEED"
    payload["vetting_verdict"] = normalize_verdict(str(verdict))
    payload.setdefault("company_name", company_name)
    payload.setdefault("salary_benchmark", "Not disclosed in retrieved sources")
    payload.setdefault("detected_tech_stack", [])
    payload.setdefault("engineering_culture", "Insufficient public detail; inferred only from the JD if present.")
    payload.setdefault("glassdoor_sentiment", "No direct review scores in sources; sector inference only.")
    payload.setdefault("recent_news_and_events", [])
    payload.setdefault("architectural_trade_offs", "See JD and official scope; not enough independent architecture write-ups.")
    payload.setdefault("red_flags", [])
    payload.setdefault("green_flags", [])
    payload.setdefault("reverse_interview_questions", [])
    payload.setdefault("source_urls", [])
    payload.setdefault("confidence", 50)
    if isinstance(payload.get("detected_tech_stack"), str):
        payload["detected_tech_stack"] = [payload["detected_tech_stack"]]
    for key in ("recent_news_and_events", "red_flags", "green_flags", "reverse_interview_questions", "source_urls"):
        if isinstance(payload.get(key), str):
            payload[key] = [payload[key]] if payload[key].strip() else []
    return payload


def _md_list(items: Sequence[str]) -> str:
    cleaned = [item.strip() for item in items if str(item).strip()]
    if not cleaned:
        return "_None recorded from available sources._"
    return "\n".join(f"- {item}" for item in cleaned)


def render_dossier_markdown(dossier: CompanyDueDiligence, backend: str) -> str:
    """Human-readable brief written next to the SQLite JSON payload."""
    sources = "\n".join(f"- {url}" for url in dossier.source_urls) or "_No URLs captured._"
    return f"""# {dossier.company_name} — Due Diligence Dossier

- **Verdict:** {dossier.vetting_verdict}
- **Confidence:** {dossier.confidence}/100
- **Backend:** `{backend}`
- **Salary benchmark:** {dossier.salary_benchmark}

## Engineering culture
{dossier.engineering_culture}

## Detected tech stack
{_md_list(dossier.detected_tech_stack)}

## Architectural trade-offs / technical debt
{dossier.architectural_trade_offs}

## Glassdoor / forum sentiment
{dossier.glassdoor_sentiment}

## Recent news and events (12–24 months)
{_md_list(dossier.recent_news_and_events)}

## Red flags
{_md_list(dossier.red_flags)}

## Green flags
{_md_list(dossier.green_flags)}

## Reverse-interview questions
{_md_list(dossier.reverse_interview_questions)}

## Sources
{sources}
"""


def export_dossier_markdown(dossier: CompanyDueDiligence, backend: str) -> Path:
    DOSSIER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = DOSSIER_OUTPUT_DIR / f"{safe_dossier_stem(dossier.company_name)}_Dossier.md"
    path.write_text(render_dossier_markdown(dossier, backend), encoding="utf-8")
    return path


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: List[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip:
            text = " ".join(data.split())
            if text:
                self._chunks.append(text)


def html_to_text(markup: str) -> str:
    parser = _TextExtractor()
    parser.feed(markup)
    return html_lib.unescape(" ".join(parser._chunks))


def _snippet(item: dict) -> str:
    body = item.get("raw_content") or item.get("content") or ""
    return body[:2500]


def filter_company_hits(hits: Sequence[dict], company_name: str) -> List[dict]:
    """Keep hits if they mention ANY generated alias."""
    aliases = [alias.lower() for alias in extract_company_aliases(company_name)]
    kept: List[dict] = []
    for item in hits:
        blob = " ".join(
            [
                str(item.get("url") or ""),
                str(item.get("title") or ""),
                str(item.get("content") or ""),
                str(item.get("raw_content") or ""),
            ]
        ).lower()
        if any(alias in blob for alias in aliases):
            kept.append(dict(item))
    return kept


def extract_official_site_content(tavily_client: TavilyClient, base_url: str) -> str:
    """Scrape key inner pages using Tavily Extract when an official domain is found."""
    clean_base = base_url.rstrip("/")
    probe_urls = [
        clean_base,
        f"{clean_base}/about",
        f"{clean_base}/about-us",
        f"{clean_base}/en/about-us",
        f"{clean_base}/en/business-solution",
        f"{clean_base}/business-solution",
    ]
    try:
        res = tavily_client.extract(urls=probe_urls)
        rows = res.get("results") if isinstance(res, dict) else getattr(res, "results", [])
        chunks: List[str] = []
        for row in rows or []:
            if isinstance(row, dict):
                raw = row.get("raw_content") or ""
            else:
                raw = getattr(row, "raw_content", "") or ""
            if raw.strip():
                chunks.append(raw[:3500])
        return "\n\n".join(chunks)
    except Exception as exc:
        print(f"⚠️ tavily.extract failed for {base_url}: {exc}")
        return ""


def official_base_urls(company_name: str, hits: Sequence[dict]) -> List[str]:
    """Identify company-owned hosts from the registry and from search result URLs."""
    bases: List[str] = []
    for host in domains_for_companies([company_name]):
        bases.append(f"https://{host.split('/', 1)[0]}")
    aliases = [a.lower().replace(" ", "") for a in extract_company_aliases(company_name) if len(a) >= 3]
    for item in hits:
        url = item.get("url") or ""
        host = extract_host(url)
        if not host:
            continue
        compact = host.replace("-", "").replace(".", "")
        if any(alias in compact or alias in host for alias in aliases):
            bases.append(f"https://{host}")
    return list(dict.fromkeys(bases))


def listing_sources(job_urls: str, job_titles: str, jd_snippets: str) -> List[dict]:
    """Use the original JD as evidence for location, stack, and work mode."""
    urls = [part.strip() for part in (job_urls or "").split(",") if part.strip()]
    titles = (job_titles or "").strip()
    snippets = (jd_snippets or "").strip()
    if not urls and not snippets:
        return []
    body = f"Related titles: {titles}\n{snippets}"
    if urls and len(snippets) < 400:
        try:
            page = fetch_page_text(urls[0])
            extracted = html_to_text(page)
            if len(extracted) > len(body):
                body = f"Related titles: {titles}\n{extracted[:8000]}"
        except Exception:
            pass
    return [
        {
            "url": urls[0] if urls else "job_postings.jd_snippet",
            "title": "Original job listing (JD)",
            "content": body[:4000],
            "raw_content": body[:8000],
        }
    ]


def wikipedia_pages(client: httpx.Client, company_name: str) -> List[dict]:
    """Public MediaWiki search + plain-text intro. No Tavily.

    # Ref: MediaWiki API action=query list=search / prop=extracts
    """
    hits: List[dict] = []
    queries = primary_search_aliases(company_name, limit=2)
    for lang in ("en", "zh"):
        for query in queries:
            search = client.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": f"{query} Hong Kong company OR engineering",
                    "srlimit": 2,
                    "format": "json",
                },
            )
            search.raise_for_status()
            titles = [
                item.get("title")
                for item in (search.json().get("query") or {}).get("search") or []
                if item.get("title")
            ]
            for title in titles:
                extract = client.get(
                    f"https://{lang}.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "prop": "extracts|info",
                        "exintro": 1,
                        "explaintext": 1,
                        "inprop": "url",
                        "titles": title,
                        "format": "json",
                        "redirects": 1,
                    },
                )
                extract.raise_for_status()
                pages = (extract.json().get("query") or {}).get("pages") or {}
                for page in pages.values():
                    if page.get("missing") is not None:
                        continue
                    url = page.get("fullurl") or (
                        f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}"
                    )
                    text = (page.get("extract") or "").strip()
                    if not text:
                        continue
                    hits.append(
                        {
                            "url": url,
                            "title": page.get("title") or title,
                            "content": text[:4000],
                            "raw_content": text[:4000],
                        }
                    )
    return hits


def wikidata_pages(client: httpx.Client, company_name: str) -> List[dict]:
    """Entity search with descriptions — more precise than open web for a named firm.

    # Ref: Wikidata wbsearchentities
    """
    search_term = primary_search_aliases(company_name, limit=1)[0]
    response = client.get(
        "https://www.wikidata.org/w/api.php",
        params={
            "action": "wbsearchentities",
            "search": search_term,
            "language": "en",
            "uselang": "en",
            "type": "item",
            "limit": 5,
            "format": "json",
        },
    )
    response.raise_for_status()
    hits: List[dict] = []
    aliases = [a.lower() for a in extract_company_aliases(company_name)]
    for item in response.json().get("search") or []:
        label = item.get("label") or ""
        description = item.get("description") or ""
        blob = f"{label} {description}".lower()
        if not any(alias in blob for alias in aliases):
            continue
        url = item.get("concepturi") or (
            f"https://www.wikidata.org/wiki/{item.get('id')}" if item.get("id") else ""
        )
        if not url:
            continue
        hits.append(
            {
                "url": url,
                "title": label,
                "content": description[:2000],
                "raw_content": description[:2000],
            }
        )
    return hits


def official_site_pages(client: httpx.Client, company_name: str) -> List[dict]:
    """Fetch About/IR pages on known first-party hosts from the employer registry."""
    hosts = domains_for_companies([company_name])
    hits: List[dict] = []
    seen: set[str] = set()
    for host in hosts[:4]:
        host_only = host.split("/", 1)[0]
        origin = f"https://{host_only}"
        for path in OFFICIAL_ABOUT_PATHS:
            url = urljoin(origin + "/", path.lstrip("/")) if path != "/" else origin + "/"
            if url in seen:
                continue
            seen.add(url)
            try:
                response = client.get(url, follow_redirects=True)
            except httpx.HTTPError:
                continue
            if response.status_code >= 400:
                continue
            ctype = response.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                continue
            text = html_to_text(response.text)[:4000]
            if len(text) < 80:
                continue
            hits.append(
                {
                    "url": str(response.url),
                    "title": f"{company_name} official page",
                    "content": text,
                    "raw_content": text,
                }
            )
            if len(hits) >= 4:
                return hits
    return hits


class DueDiligenceAgent:
    def __init__(
        self,
        deepseek_api_key: str,
        tavily_api_key: Optional[str] = None,
        db_path: Optional[str] = None,
        backend: Optional[str] = None,
    ):
        self.backend = (backend or os.environ.get("DUE_DILIGENCE_BACKEND") or "").strip().lower()
        if self.backend not in {"official", "tavily", ""}:
            raise ValueError("DUE_DILIGENCE_BACKEND must be 'official' or 'tavily'")
        self.tavily = None
        if self.backend == "":
            self.backend = "tavily" if tavily_api_key else "official"
        if self.backend == "tavily":
            if not tavily_api_key:
                raise ValueError("TAVILY_API_KEY is required when DUE_DILIGENCE_BACKEND=tavily")
            self.tavily = TavilyClient(api_key=tavily_api_key)
        self.chat_model = os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_CHAT_MODEL)
        self.client = instrument_openai(
            OpenAI(api_key=deepseek_api_key, base_url=DEEPSEEK_BASE_URL)
        )
        self.db_manager = JobDBManager(db_path=db_path) if db_path else JobDBManager()
        self.candidate_profile = load_master_profile()
        self._http = httpx.Client(
            headers={"User-Agent": HTTP_USER_AGENT},
            timeout=20.0,
            follow_redirects=True,
        )

    def _mark_job_expired(self, job: dict, reason: str) -> None:
        job_id = int(job["id"])
        self.db_manager.set_job_expired(job_id, True)
        title = job.get("job_title") or ""
        company = job.get("company_name") or ""
        print(f"⌛ [Expired] job #{job_id} {title} — {reason}")
        log_activity("Dana", f"Marked expired job #{job_id}: {title} ({reason})")
        notify_job_update(
            "Dana",
            "Listing expired",
            company=company,
            title=title,
            extra=reason,
            url=job.get("job_url") or "",
        )

    def check_listing_still_open(self, job: dict) -> bool:
        """GET the stored URL. Expire gone listings; keep unknown network errors.

        # Ref: Dana must not research a company whose vacancy is already dead
        """
        stored = (job.get("job_url") or "").strip()
        url = normalize_listing_url(stored)
        title = job.get("job_title") or ""
        shape = listing_url_problem(url)
        if shape:
            still, expire, reason = listing_check_verdict(shape, None, None, None)
            if expire:
                self._mark_job_expired(job, reason)
            return still
        try:
            response = self._http.get(url)
            status = int(response.status_code)
            if status == 400 and "hkjc.com" in url.lower() and "/en_US/job/" not in url:
                retry = normalize_listing_url(url)
                if retry != url:
                    response = self._http.get(retry)
                    url = retry
                    status = int(response.status_code)
            http_ok = 200 <= status < 300
            title_found: Optional[bool] = None
            if http_ok:
                page = html_to_text(response.text or "")
                title_found = listing_text_supports_title(page, title)
            still, expire, reason = listing_check_verdict(
                None, http_ok, status, title_found
            )
        except httpx.HTTPError as exc:
            still, expire, reason = listing_check_verdict(None, False, None, None)
            reason = f"{reason}: {exc}"
        if expire:
            self._mark_job_expired(job, reason)
        elif not still:
            print(
                f"⚠️  [Listing check] job #{job.get('id')} skipped (not expired): {reason}"
            )
        return still

    def live_jobs_for_research(
        self,
        company_name: str,
        min_score: int = MIN_MATCH_SCORE,
    ) -> List[dict]:
        """Drop dead vacancies, then return jobs still listed for this employer."""
        live: List[dict] = []
        for job in self.db_manager.list_active_jobs_for_company(
            company_name, min_score=min_score
        ):
            if self.check_listing_still_open(job):
                live.append(job)
        return live

    def _search_queries(self, company_name: str) -> List[str]:
        return [
            f'"{company_name}" Hong Kong company overview operations',
            f'"{company_name}" Hong Kong news layoffs funding regulation',
            f'"{company_name}" Hong Kong employer culture careers technology',
        ]

    def _tavily_lanes(self, company_name: str) -> List[tuple[str, List[str], str]]:
        """Split Tavily calls so Glassdoor/news/forums are not drowned by official homepages."""
        employer_hosts = domains_for_companies([company_name])
        lanes: List[tuple[str, List[str], str]] = []
        for alias in primary_search_aliases(company_name, limit=2):
            quoted = f'"{alias}"'
            lanes.extend(
                [
                    (
                        "news",
                        HK_NEWS_DOMAINS,
                        f"{quoted} tender OR 項目 OR 裁員 OR 牌照 Hong Kong",
                    ),
                    (
                        "sentiment",
                        SENTIMENT_DOMAINS,
                        f"{quoted} reviews OR 工時 OR OT OR 評價 Hong Kong",
                    ),
                    (
                        "tech",
                        TECH_FORUM_DOMAINS + employer_hosts,
                        f'{quoted} IIoT OR "Smart Site Safety" OR SCADA OR telemetry OR software OR architecture',
                    ),
                ]
            )
        lanes.append(
            (
                "general",
                list(dict.fromkeys(HK_RESEARCH_DOMAINS + employer_hosts)),
                f'"{primary_search_aliases(company_name, limit=1)[0]}" Hong Kong company overview',
            )
        )
        return lanes

    def search_company_background(
        self,
        company_name: str,
        force_refresh: bool = False,
        job_urls: str = "",
        job_titles: str = "",
        jd_snippets: str = "",
    ) -> List[dict]:
        """Retrieve public background text, then attach the original JD as evidence."""
        if not is_usable_company_name(company_name):
            return listing_sources(job_urls, job_titles, jd_snippets)

        cache_key = research_cache_key(company_name, self.backend)
        if not force_refresh:
            cached = self.db_manager.get_search_cache(cache_key, SEARCH_CACHE_MAX_AGE_DAYS)
            if cached is not None:
                print(f"♻️  [Cache hit] retrieval skipped for {company_name} ({self.backend})")
                merged = {item.get("url"): item for item in cached if item.get("url")}
                for item in listing_sources(job_urls, job_titles, jd_snippets):
                    merged[item["url"]] = item
                return list(merged.values())

        if self.backend == "official":
            results = self._search_official(company_name)
        else:
            results = self._search_tavily(company_name)
            results.extend(self._deep_extract_official_sites(company_name, results))
            for item in self._search_official(company_name):
                if item.get("url"):
                    results.append(item)
        results = filter_company_hits(results, company_name)
        self.db_manager.save_search_cache(cache_key, company_name, results)
        merged = {item.get("url"): item for item in results if item.get("url")}
        for item in listing_sources(job_urls, job_titles, jd_snippets):
            merged[item["url"]] = item
        return list(merged.values())

    def _search_official(self, company_name: str) -> List[dict]:
        print(f"🔍 [Research:official] Wikipedia + Wikidata + first-party sites for {company_name}")
        merged: Dict[str, dict] = {}
        try:
            for item in wikipedia_pages(self._http, company_name):
                merged[item["url"]] = item
        except httpx.HTTPError as exc:
            print(f"⚠️ Wikipedia lookup failed: {exc}")
        try:
            for item in wikidata_pages(self._http, company_name):
                merged[item["url"]] = item
        except httpx.HTTPError as exc:
            print(f"⚠️ Wikidata lookup failed: {exc}")
        try:
            for item in official_site_pages(self._http, company_name):
                merged[item["url"]] = item
        except httpx.HTTPError as exc:
            print(f"⚠️ Official-site fetch failed: {exc}")
        return list(merged.values())

    def _search_tavily(self, company_name: str) -> List[dict]:
        merged: Dict[str, dict] = {}
        assert self.tavily is not None
        for lane_name, domains, query in self._tavily_lanes(company_name):
            include_domains = list(dict.fromkeys(domains))
            print(f"🔍 [Research:tavily:{lane_name}] {query}")
            log_activity("Dana", f"Searching {lane_name} lane for {company_name}")
            try:
                response = self.tavily.search(
                    query=query,
                    include_domains=include_domains or None,
                    search_depth="advanced",
                    max_results=5,
                    time_range="year",
                    include_raw_content="markdown",
                )
            except Exception as exc:
                print(f"⚠️ [Tavily research {lane_name} failed] {exc}")
                log_activity(
                    "Dana",
                    f"Tavily {lane_name} failed: {exc}",
                    level="WARN",
                )
                continue
            for item in response.get("results") or []:
                url = item.get("url")
                if url:
                    merged[url] = item
        return filter_company_hits(list(merged.values()), company_name)

    def _deep_extract_official_sites(
        self, company_name: str, hits: Sequence[dict]
    ) -> List[dict]:
        """Replace shallow homepage snippets with Tavily Extract body text."""
        if self.tavily is None:
            return []
        extracted: List[dict] = []
        for base in official_base_urls(company_name, hits)[:3]:
            print(f"🔎 [tavily.extract] {base}")
            log_activity("Dana", f"Tavily extract: {base}")
            text = extract_official_site_content(self.tavily, base)
            if len(text) < 120:
                continue
            extracted.append(
                {
                    "url": base,
                    "title": f"{company_name} official site (extracted)",
                    "content": text[:4000],
                    "raw_content": text[:8000],
                }
            )
        return extracted

    def _request_dossier_json(self, system_prompt: str, user_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        return (response.choices[0].message.content or "").strip()

    def distill_dossier(
        self,
        company_name: str,
        job_titles: str,
        search_hits: Sequence[dict],
    ) -> Optional[CompanyDueDiligence]:
        sources_blob = compact_research_blob(search_hits)
        example = json.dumps(DOSSIER_JSON_EXAMPLE, ensure_ascii=False, indent=2)
        system_prompt = f"""
You are a Hong Kong market due-diligence analyst writing an actionable engineering hiring brief.
Evaluate the company using both the retrieved web excerpts and the attached Job Description (JD).

Core Rules:
1. Grounded Contextual Inference: If direct Glassdoor/Blind numerical scores are unavailable, analyze the engineering culture, operational model (e.g., public tender contractor, enterprise vendor), and tech stack inferred from the JD requirements and official business scopes.
2. In 'architectural_trade_offs', explicitly evaluate challenges related to legacy platforms, hardware-software integration, cloud-to-edge connectivity, or data telemetry implied by the job.
3. In 'glassdoor_sentiment', if direct reviews are missing, summarize the likely workplace rhythm (e.g., project deadlines, compliance overhead) based on the company's operating sector. Label that as sector inference, not as a Glassdoor score.
4. Output must be a single valid JSON object with exactly these keys: {list(DOSSIER_JSON_EXAMPLE.keys())}.
5. company_name must be the real employer. vetting_verdict must be exactly PROCEED or AVOID.
6. Do not invent numeric Glassdoor ratings, salary figures, or layoff counts that are not in the excerpts.
7. Write reverse_interview_questions as 3-5 senior architecture/org questions.
8. BILINGUAL OUTPUT: Write engineering_culture, glassdoor_sentiment, architectural_trade_offs, and all list items (red_flags, green_flags, reverse_interview_questions, recent_news_and_events) in BOTH English and Traditional Chinese. Format: "English. 繁體中文。" Each list item bilingual.
9. JSON hygiene: escape every double-quote inside strings; no trailing commas; no markdown fences; keep each string under 400 characters; keep each list at most 8 items.

Example JSON shape:
{example}

Candidate profile:
{profile_brief(self.candidate_profile)}
{milo_readme_prompt_block(DEFAULT_PROFILE_PATH)}
Research backend: {self.backend}
"""
        user_prompt = (
            f"Company: {company_name}\n"
            f"Aliases: {', '.join(extract_company_aliases(company_name))}\n"
            f"Related roles: {job_titles}\n\n"
            f"JOB DESCRIPTION AND WEB EXCERPTS:\n{sources_blob}"
        )
        raw = self._request_dossier_json(system_prompt, user_prompt)
        for attempt in (1, 2):
            if not raw:
                print(f"⚠️ [JSON empty] {company_name}")
                return None
            try:
                payload = coerce_dossier_payload(raw, company_name)
                return CompanyDueDiligence.model_validate(payload)
            except Exception as exc:
                fail_path = dump_parse_failure(company_name, raw, exc)
                print(f"⚠️ [JSON parse failed attempt {attempt}] {company_name}: {exc}")
                print(f"   raw LLM output saved: {fail_path}")
                log_activity(
                    "Dana",
                    f"JSON parse failed for {company_name}: {exc}",
                    level="WARN",
                )
                if attempt == 1:
                    raw = self._request_dossier_json(
                        system_prompt
                        + "\nCRITICAL: The previous JSON was invalid. Return compact valid JSON only.",
                        (
                            f"Parse error: {exc}\n"
                            "Rewrite the SAME dossier as valid JSON. Escape inner quotes. "
                            "Keep strings short.\n"
                            f"Company: {company_name}\n"
                            f"Broken JSON:\n{raw[:12000]}"
                        ),
                    )
        return None

    def research_company(
        self,
        company_name: str,
        job_titles: str = "",
        job_urls: str = "",
        jd_snippets: str = "",
        force_refresh: bool = False,
        min_score: int = MIN_MATCH_SCORE,
    ) -> Optional[CompanyDueDiligence]:
        if not is_usable_company_name(company_name):
            print(f"⏭️  [Skip] cannot research placeholder employer: {company_name!r}")
            return None
        live = self.live_jobs_for_research(company_name, min_score=min_score)
        if not live:
            print(
                f"⏭️  [Skip] no live listings left for {company_name} "
                "(expired or unreachable this run)"
            )
            log_activity(
                "Dana",
                f"Skipped research for {company_name}: no live job listings",
            )
            return None
        job_titles = ", ".join(
            dict.fromkeys(j["job_title"] for j in live if j.get("job_title"))
        )
        job_urls = " ".join(dict.fromkeys(j["job_url"] for j in live if j.get("job_url")))
        jd_snippets = "\n".join(j.get("jd_snippet") or "" for j in live)
        if not force_refresh and self.db_manager.has_current_dossier(company_name):
            print(f"♻️  [Cache hit] deep dossier already stored for {company_name}")
            return None
        log_activity("Dana", f"Research started for {company_name}")
        hits = self.search_company_background(
            company_name,
            force_refresh=force_refresh,
            job_urls=job_urls,
            job_titles=job_titles,
            jd_snippets=jd_snippets,
        )
        log_activity("Dana", f"Distilling dossier via DeepSeek for {company_name}")
        dossier = self.distill_dossier(company_name, job_titles, hits)
        if not dossier:
            return None
        if not is_usable_company_name(dossier.company_name):
            dossier.company_name = company_name
        dossier.vetting_verdict = normalize_verdict(dossier.vetting_verdict)
        if not dossier.source_urls:
            dossier.source_urls = [item.get("url", "") for item in hits if item.get("url")]
        md_path = export_dossier_markdown(dossier, self.backend)
        self.db_manager.save_dossier(company_name, dossier.model_dump(), markdown_path=str(md_path))
        log_activity(
            "Dana",
            f"Dossier saved: {dossier.company_name} | {dossier.vetting_verdict} | "
            f"confidence={dossier.confidence}",
        )
        notify_job_update(
            "Dana",
            f"Dossier {dossier.vetting_verdict}",
            company=dossier.company_name,
            title=job_titles.split(",")[0].strip() if job_titles else "",
            extra=f"confidence={dossier.confidence}",
            url=(job_urls.split()[0] if job_urls else ""),
        )
        print(
            f"📁 [Dossier] {dossier.company_name} | {dossier.vetting_verdict} | "
            f"confidence={dossier.confidence} | {md_path}"
        )
        return dossier

    def repair_anonymous_jobs(self, min_score: int = MIN_MATCH_SCORE) -> List[str]:
        """Recover real employer names from listing pages and drop placeholder dossiers."""
        recovered: List[str] = []
        for job in self.db_manager.list_jobs_missing_employer(min_score=min_score):
            resolved = resolve_employer_name(job["job_url"], job["jd_snippet"])
            if not resolved:
                resolved = self._extract_employer_llm(job)
            if not resolved:
                print(f"⚠️ Still anonymous: {job['job_title']} ({job['job_url']})")
                continue
            print(f"🏷️  [Backfill employer] job #{job['id']} {job['company_name']!r} → {resolved}")
            self.db_manager.delete_dossier(job["company_name"])
            self.db_manager.update_job_company_name(job["id"], resolved)
            recovered.append(resolved)
        return list(dict.fromkeys(recovered))

    def _extract_employer_llm(self, job: dict) -> Optional[str]:
        """Last resort: read the listing page and name the employer. Empty if truly hidden."""
        try:
            page = fetch_page_text(job["job_url"])
        except Exception:
            page = job.get("jd_snippet") or ""
        text = html_to_text(page) if "<" in page else page
        response = self.client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract the hiring employer's real name from this Hong Kong job listing. "
                        'Return JSON {"company_name":""} if the employer is confidential or absent. '
                        "Never return Not Disclosed, Unknown, or Confidential."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Title: {job.get('job_title')}\n\n{text[:6000]}",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content
        if not raw:
            return None
        try:
            payload = json.loads(parse_json_payload(raw))
        except (json.JSONDecodeError, ValueError):
            return None
        name = str(payload.get("company_name") or "").strip()
        return name if is_usable_company_name(name) else None

    def run_pipeline(
        self,
        min_score: int = MIN_MATCH_SCORE,
        force_refresh: bool = False,
        company: Optional[str] = None,
        job_id: Optional[int] = None,
    ) -> int:
        """Research high-match employers. Optionally limit to one company or one job id."""
        if job_id is not None:
            job = self.db_manager.get_job_by_id(job_id)
            if not job:
                print(f"❌ No job_postings row with id={job_id}")
                return 0
            if not passes_dana_composite_gate(job.get("match_score") or 0, min_score):
                print(
                    f"⏭️  [Skip] job #{job_id} composite={job.get('match_score')} "
                    f"< min composite {min_score}"
                )
                log_activity(
                    "Dana",
                    f"Skipped job #{job_id}: composite below {min_score}",
                )
                return 0
            company_name = job["company_name"]
            if not is_usable_company_name(company_name):
                resolved = resolve_employer_name(job["job_url"], job["jd_snippet"])
                if not resolved:
                    resolved = self._extract_employer_llm(job)
                if not resolved:
                    print(f"⚠️ Job #{job_id} still has no employer name.")
                    return 0
                self.db_manager.delete_dossier(company_name)
                self.db_manager.update_job_company_name(job_id, resolved)
                company_name = resolved
            result = self.research_company(
                company_name,
                job_titles=job["job_title"],
                job_urls=job["job_url"],
                jd_snippets=job["jd_snippet"],
                force_refresh=True,
                min_score=min_score,
            )
            written = 1 if result else 0
            print(f"\n✅ 單筆調查完成！新增 {written} 份 company_dossiers。")
            log_activity("Dana", f"Pipeline complete: {written} dossiers written")
            notify_job_update(
                "Dana",
                "Research finished",
                extra=f"{written} dossier(s) written",
            )
            return written

        recovered = self.repair_anonymous_jobs(min_score=min_score)
        pending = self.db_manager.list_companies_pending_diligence(
            min_score=min_score,
            include_existing=force_refresh,
        )
        if company:
            needle = company.strip().lower()
            pending = [
                row for row in pending
                if needle in (row["company_name"] or "").lower()
            ]
        if not pending:
            print("✅ 沒有待調查公司（檢查 --company / --job-id 或快取）。")
            return 0
        written = 0
        for row in pending:
            result = self.research_company(
                row["company_name"],
                job_titles=row.get("job_titles") or "",
                job_urls=row.get("job_urls") or "",
                jd_snippets=row.get("jd_snippets") or "",
                force_refresh=force_refresh or row["company_name"] in recovered,
            )
            if result:
                written += 1
        print(f"\n✅ 背景調查完成！新增 {written} 份 company_dossiers（JSON + Markdown）。")
        log_activity("Dana", f"Pipeline complete: {written} dossiers written")
        notify_job_update(
            "Dana",
            "Research finished",
            extra=f"{written} dossier(s) written",
        )
        return written


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hong Kong employer due-diligence agent")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="Re-run Tavily/DeepSeek even when a current dossier exists",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=MIN_MATCH_SCORE,
        help="Minimum stored composite (match_score) before research (default 80)",
    )
    parser.add_argument(
        "--job-id",
        type=int,
        default=None,
        help="Research only this job_postings.id (e.g. 1)",
    )
    parser.add_argument(
        "--company",
        type=str,
        default=None,
        help="Research only companies whose name contains this text (e.g. ATAL)",
    )
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    from env_keys import deepseek_api_key, tavily_api_key
    tavily_key = tavily_api_key()
    deepseek_key = deepseek_api_key()
    backend = (os.environ.get("DUE_DILIGENCE_BACKEND") or "").strip().lower()
    if backend not in {"official", "tavily"}:
        backend = "tavily" if tavily_key else "official"
    if not deepseek_key:
        raise SystemExit("Set DEEPSEEK_API_KEY in the environment or a .env file.")
    if backend == "tavily" and not tavily_key:
        raise SystemExit("Set TAVILY_API_KEY, or set DUE_DILIGENCE_BACKEND=official.")
    print(f"Using DUE_DILIGENCE_BACKEND={backend}")
    agent = DueDiligenceAgent(
        deepseek_api_key=deepseek_key,
        tavily_api_key=tavily_key or None,
        backend=backend,
    )
    agent.run_pipeline(
        min_score=args.min_score,
        force_refresh=args.force_refresh,
        company=args.company,
        job_id=args.job_id,
    )
    from llm_usage import finalize_usage
    finalize_usage("Dana")
