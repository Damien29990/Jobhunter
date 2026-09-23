"""Hong Kong talent-scout agent: search trusted job boards, ATS hosts, and employer career sites."""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import math
import os
import re
import sqlite3
import struct
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
import sqlite_vec
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field
from tavily import TavilyClient
from listing_filters import (  # noqa: E402
    is_academic_non_job_url,
    is_academic_programme_title,
    is_job_posting_url,
    is_jobsdb_category_url,
    is_hkstp_listing_url,
    is_junk_job_title,
    jobsdb_postings_from_listing_text,
    hkstp_postings_from_listing_text,
    listing_text_supports_title,
    listing_url_problem,
    normalize_listing_url,
    prefer_listing_title,
    title_from_job_url,
    display_listing_title,
)
from llm_usage import instrument_openai  # noqa: E402

_VALIDATORS_DIR = Path(__file__).resolve().parent.parent / "validators"
if str(_VALIDATORS_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATORS_DIR))

# Ref: Asia/Hong_Kong (UTC+8) ISO 8601
HK_TZ = ZoneInfo("Asia/Hong_Kong")

# Tavily Search include_domains max is 300; keep each lane short for ranking quality.
# Ref: Tavily Search API — include_domains, time_range, include_raw_content
TAVILY_MAX_INCLUDE_DOMAINS = 300
DEFAULT_TIME_RANGE = "week"
MAX_JOB_AGE_DAYS = 14
MAX_JOBSDB_CATEGORY_EXPAND_PER_SEARCH = 2
MAX_JOBSDB_POSTINGS_PER_CATEGORY = 6
MAX_HKSTP_LISTING_EXPAND_PER_SEARCH = 2
MAX_HKSTP_POSTINGS_PER_LISTING = 6

# DeepSeek Chat Completions is OpenAI-SDK compatible. No embeddings API.
# Ref: https://api.deepseek.com — use V4 model IDs after deepseek-chat retirement (2026-07-24)
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_CHAT_MODEL = "deepseek-v4-flash"
EMBEDDING_DIM = 1536
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = str(PROJECT_ROOT / "job_agent.db")
DEFAULT_PROFILE_PATH = PROJECT_ROOT / "config" / "master_profile.json"


# ---------------------------------------------------------------------------
# 1. Trusted sources — split by lane so Tavily is not asked to rank 80 hosts
#    in one call (docs: keep include_domains short and relevant).
# ---------------------------------------------------------------------------

# Public Hong Kong job boards. Verified 2026 market coverage:
# JobsDB (SEEK) is the volume leader; CTgoodjobs is the main local/Chinese board;
# Labour Department IES and CSB are official government portals;
# HKSTP Talent Pool lists Science Park tenant vacancies.
# Ref: HoiSum HK Job Boards Guide 2026; Labour Department IES; Civil Service Bureau
# Own Tavily lane: mixed-board searches bury JobsDB under LinkedIn/CTgoodjobs,
# and JobsDB hits are almost always SEO category pages, not /job/{id}.
JOBSDB_BOARDS: List[str] = [
    "hk.jobsdb.com",
    "jobsdb.com",
]
HK_JOB_BOARDS: List[str] = [
    "ctgoodjobs.hk",
    "linkedin.com/jobs",
    "efinancialcareers.hk",
    "efinancialcareers.com",
    "recruit.com.hk",
    "cpjobs.com",
    "jobs.gov.hk",
    "ejs.labour.gov.hk",
    "csb.gov.hk",
    "hkicpa.org.hk",
    "techinasia.com/jobs",
    "talentjobseeker.hkstp.org",
]

# Shared ATS hosts. Large HK employers (banks, Big 4, MNCs, tech) often do not
# post on JobsDB at all — roles live only on Workday / Greenhouse / SuccessFactors.
# Tavily matches subdomains, so myworkdayjobs.com covers hsbc.wd3.myworkdayjobs.com.
# Ref: HoiSum ATS Resume Guide for Hong Kong 2026
ATS_PLATFORMS: List[str] = [
    "myworkdayjobs.com",
    "boards.greenhouse.io",
    "job-boards.greenhouse.io",
    "jobs.lever.co",
    "ashbyhq.com",
    "jobs.ashbyhq.com",
    "successfactors.com",
    "successfactors.eu",
    "taleo.net",
    "smartrecruiters.com",
    "icims.com",
    "jobs.jobvite.com",
    "eightfold.ai",
    "ultipro.com",
    "dayforcehcm.com",
]

# First-party career sites for large HK organisations. These are not job boards:
# each employer runs its own catalogue, often with listings that never appear
# on JobsDB / LinkedIn. Hosts are corporate career domains, not marketing homepages.
# Ref: employer career portals (HSBC, Cathay, MTR, CSB, universities)
HK_EMPLOYER_CAREER_SITES: Dict[str, List[str]] = {
    "hsbc": ["hsbc.com/careers", "careers.hsbc.com"],
    "hang seng": ["hangseng.com"],
    "standard chartered": ["sc.com/en/careers", "sc.com"],
    "bank of china hong kong": ["bochk.com"],
    "bank of east asia": ["hkbea.com"],
    "dbs": ["dbs.com"],
    "citi": ["careers.citigroup.com", "jobs.citi.com"],
    "jpmorgan": ["careers.jpmorgan.com", "jpmorganchase.com/careers"],
    "goldman sachs": ["goldmansachs.com/careers"],
    "morgan stanley": ["morganstanley.com/careers"],
    "ubs": ["ubs.com/careers"],
    "pwc": ["pwc.com/careers", "jobs.pwc.com"],
    "deloitte": ["deloitte.com/careers"],
    "ey": ["ey.com/careers"],
    "kpmg": ["kpmg.com/careers"],
    "cathay pacific": ["careers.cathaypacific.com"],
    "mtr": ["mtr.com.hk"],
    "clp": ["clp.com.hk", "careers.clpgroup.com"],
    "hkex": ["hkex.com.hk", "hkexgroup.com"],
    "airport authority": ["hongkongairport.com"],
    "aia": ["careers.aia.com", "aia.com.hk"],
    "manulife": ["manulife.com.hk"],
    "prudential": ["prudential.com.hk"],
    "swire": ["swire.com", "careers.swire.com"],
    "jardine": ["jardines.com"],
    "ck hutchison": ["ckh.com.hk"],
    "hkt": ["hkt.com", "pccw.com", "job.pccw.com"],
    "hong kong jockey club": ["hkjc.com", "careers.hkjc.com"],
    "hospital authority": ["ha.org.hk"],
    "hku": ["jobs.hku.hk"],
    "cuhk": ["hro.cuhk.edu.hk"],
    "hkust": ["career.hkust.edu.hk"],
    "polyu": ["polyu.edu.hk/hro"],
    "cityu": ["cityu.edu.hk/hro"],
    "google": ["careers.google.com"],
    "microsoft": ["careers.microsoft.com"],
    "amazon": ["amazon.jobs"],
    "apple": ["jobs.apple.com"],
    "tencent": ["careers.tencent.com"],
    "alibaba": ["careers.alibaba.com"],
    "bytedance": ["jobs.bytedance.com", "lifeattiktok.com"],
    "atal": ["atal.com.hk", "atal.com"],
}

# Aggregators (Indeed, Glassdoor, Wellfound) are intentionally excluded from
# the default whitelist: high duplicate/ghost-posting rate, weaker HK verification.
# Pass extra_domains=... if a specific search needs them.

SEARCH_LANES: Dict[str, List[str]] = {
    "jobsdb": JOBSDB_BOARDS,
    "hk_job_boards": HK_JOB_BOARDS,
    "ats_platforms": ATS_PLATFORMS,
    "hk_employer_careers": sorted(
        {host for hosts in HK_EMPLOYER_CAREER_SITES.values() for host in hosts}
    ),
}


# ---------------------------------------------------------------------------
# 2. Deterministic URL / domain validators (no LLM guessing)
# ---------------------------------------------------------------------------

def extract_host(url: str) -> str:
    """Return lowercase hostname without leading www.

    # Ref: urllib.parse — used to classify job URL provenance
    """
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.netloc or parsed.path.split("/")[0]).lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _host_matches(host: str, pattern: str) -> bool:
    """Match a Tavily-style domain or host/path pattern against a URL host."""
    pattern_host = pattern.split("/", 1)[0].lower()
    if pattern_host.startswith("www."):
        pattern_host = pattern_host[4:]
    return host == pattern_host or host.endswith(f".{pattern_host}")


def is_ats_host(host: str) -> bool:
    """True if the host is a shared ATS platform (Workday, Greenhouse, …).

    # Ref: HoiSum ATS Resume Guide for Hong Kong 2026
    """
    return any(_host_matches(host, pattern) for pattern in ATS_PLATFORMS)


def flatten_trusted_patterns() -> List[str]:
    """All default include_domains patterns across lanes."""
    seen: List[str] = []
    for lane_domains in SEARCH_LANES.values():
        for pattern in lane_domains:
            if pattern not in seen:
                seen.append(pattern)
    return seen


def is_trusted_job_url(url: str, extra_domains: Sequence[str] = ()) -> bool:
    """Accept only whitelist job boards, ATS hosts, or named employer career sites.

    # Ref: trusted-source policy — drop aggregators and unknown recruiter microsites
    """
    host = extract_host(url)
    if not host:
        return False
    patterns = flatten_trusted_patterns() + list(extra_domains)
    return any(_host_matches(host, pattern) for pattern in patterns)


def is_recently_posted(published_date: Optional[str], max_age_days: int = 14) -> bool:
    """True if a Tavily published_date is within max_age_days. None = pass (unknown age).

    # Ref: Tavily search result published_date (ISO 8601)
    """
    if not published_date:
        return True  # don't reject just because the board doesn't expose a date
    try:
        from datetime import datetime
        published = datetime.fromisoformat(published_date.replace("Z", "+00:00"))
        if published.tzinfo is None:
            published = published.replace(tzinfo=HK_TZ)
        age_days = (datetime.now(HK_TZ) - published.astimezone(HK_TZ)).days
        return age_days <= max_age_days
    except (ValueError, TypeError):
        return True  # unparseable date — don't block


def domains_for_companies(company_names: Sequence[str]) -> List[str]:
    """Map target employer names to known first-party career hosts.

    # Ref: HK_EMPLOYER_CAREER_SITES registry
    """
    found: List[str] = []
    for name in company_names:
        key = name.strip().lower()
        if key in HK_EMPLOYER_CAREER_SITES:
            found.extend(HK_EMPLOYER_CAREER_SITES[key])
            continue
        for alias, hosts in HK_EMPLOYER_CAREER_SITES.items():
            if alias in key or key in alias:
                found.extend(hosts)
    # Preserve order, drop duplicates
    return list(dict.fromkeys(found))


def looks_like_official_career_url(url: str, company_hint: str = "") -> bool:
    """Heuristic for a first-party careers page discovered at search time.

    Accepts known ATS hosts, careers/jobs subdomains, or company-slug hosts
    whose path looks like a jobs catalogue.
    """
    host = extract_host(url)
    path = urlparse(url if "://" in url else f"https://{url}").path.lower()
    if is_ats_host(host):
        return True
    career_host_tokens = ("career", "careers", "jobs", "recruit", "talent")
    if any(token in host.split(".")[0] for token in career_host_tokens):
        return True
    slug = "".join(ch for ch in company_hint.lower() if ch.isalnum())
    host_compact = host.replace(".", "").replace("-", "")
    if slug and len(slug) >= 4 and slug in host_compact:
        if any(token in path for token in ("/career", "/careers", "/jobs", "/join-us", "/join")):
            return True
    return False


def lexical_embedding(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
    """Feature-hashed token embedding (L2-normalised).

    DeepSeek does not expose an embeddings endpoint; calling OpenAI
    text-embedding-3-small would hit the same HK 403. This keeps sqlite-vec
    working fully offline.
    """
    vec = [0.0] * dim
    for raw in text.lower().split():
        token = "".join(ch for ch in raw if ch.isalnum())
        if not token:
            continue
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def parse_json_payload(raw: str) -> str:
    """Strip markdown fences so Pydantic can validate DeepSeek JSON mode output."""
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        return fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def now_hk_iso() -> str:
    """Current time in Asia/Hong_Kong, ISO 8601 with offset.

    # Ref: timezone standard — Asia/Hong_Kong (UTC+8)
    """
    return datetime.now(HK_TZ).isoformat()


def summarize_jd(client, chat_model: str, jd_text: str, max_chars: int = 600) -> str:
    """Use DeepSeek to create a precise 2-3 sentence JD summary.

    Extracts: role title, key tech requirements, location, salary, company hints.
    Falls back to jd_text[:max_chars] if the LLM call fails.

    # Ref: replaces crude content[:500] truncation
    """
    if not (jd_text or "").strip():
        return ""
    try:
        response = client.chat.completions.create(
            model=chat_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Summarize this job description in 2-3 precise sentences. "
                        "Capture: job title, required tech stack, years of experience, "
                        "location, salary if stated, and any special requirements. "
                        "Be factual — do not invent details."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        'Return JSON {"summary": "..."} only.\n\n'
                        f"JOB DESCRIPTION:\n{jd_text[:8000]}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content or ""
        payload = json.loads(parse_json_payload(raw))
        summary = str(payload.get("summary") or "").strip()
        if summary:
            return summary[:max_chars]
    except Exception as exc:
        print(f"⚠️ [summarize_jd fallback] {exc}")
    return jd_text[:max_chars]


def passes_score_gate(score: int, min_score: int) -> bool:
    """Deterministic match-score threshold. Do not let the LLM override this."""
    return score >= min_score


PIVOT_TRANSFERABILITY_FLOOR = 85
COMPOSITE_HARD_SKILL_WEIGHT = 0.55
COMPOSITE_TRANSFERABILITY_WEIGHT = 0.45


def compute_composite_match_score(hard_skill_score: int, transferability_score: int) -> int:
    """Weighted dual-score. LLM scores are inputs; the blend is not guessed.

    # Ref: career-architect matrix — 55% hard-skill / 45% transferability
    """
    hard = max(0, min(100, int(hard_skill_score)))
    transfer = max(0, min(100, int(transferability_score)))
    blended = (
        COMPOSITE_HARD_SKILL_WEIGHT * hard
        + COMPOSITE_TRANSFERABILITY_WEIGHT * transfer
    )
    return max(0, min(100, int(round(blended))))


def passes_dual_score_gate(
    composite_score: int,
    transferability_score: int,
    min_score: int = 75,
    pivot_floor: int = PIVOT_TRANSFERABILITY_FLOOR,
) -> bool:
    """Keep strong skill matches and high-transfer career pivots.

    Rex may store jobs that fail this gate. Dana does not use this OR-bypass.
    # Ref: dual-score gate — composite >= min_score OR transferability >= 85
    """
    return composite_score >= min_score or transferability_score >= pivot_floor


def passes_dana_composite_gate(composite_score: int, min_score: int = 80) -> bool:
    """Dana researches only jobs at/above the min composite (stored as match_score).

    Transferability ≥ 85 is not a substitute.
    # Ref: user — Dana queue is min composite only
    """
    return int(composite_score or 0) >= int(min_score)


_PLACEHOLDER_COMPANY_NAMES = {
    "not disclosed",
    "undisclosed",
    "unknown",
    "n/a",
    "na",
    "confidential",
    "公司保密",
    "未披露",
    "保密",
    "hidden",
    "anonymous",
}


def is_usable_company_name(name: str) -> bool:
    """Reject anonymous/placeholder employer names so dossiers are real companies.

    # Ref: CTgoodjobs and similar boards often hide the employer
    """
    key = " ".join((name or "").strip().lower().split())
    return len(key) >= 2 and key not in _PLACEHOLDER_COMPANY_NAMES


_COMPANY_STOPWORDS = {
    "hong", "kong", "limited", "ltd", "inc", "plc", "group", "holdings",
    "the", "co", "company", "corporation", "corp", "international", "asia",
    "hk", "sar", "china",
}

_ORG_LABEL_RE = re.compile(
    r"(?is)(?:hiringOrganization|companyName|employer|"
    r"公司(?:名稱|名字)?|僱主|雇主|招聘企業)\s*[:：\"']+\s*([^\n\"'<|]{2,80})"
)


def significant_company_tokens(name: str) -> List[str]:
    """Tokens used to verify a source is actually about this employer."""
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9]{1,}|[\u4e00-\u9fff]{2,}", name)
    out: List[str] = []
    for token in tokens:
        folded = token.lower()
        if folded in _COMPANY_STOPWORDS:
            continue
        if folded in _PLACEHOLDER_COMPANY_NAMES:
            continue
        out.append(folded)
    return out


def source_mentions_company(text: str, company_name: str) -> bool:
    blob = (text or "").lower()
    if not blob:
        return False
    if company_name.lower() in blob:
        return True
    tokens = significant_company_tokens(company_name)
    if not tokens:
        return False
    return all(token in blob for token in tokens[:2]) if len(tokens) >= 2 else tokens[0] in blob


def _iter_json_ld_objects(payload: object) -> List[dict]:
    found: List[dict] = []
    if isinstance(payload, dict):
        found.append(payload)
        graph = payload.get("@graph")
        if isinstance(graph, list):
            for node in graph:
                found.extend(_iter_json_ld_objects(node))
    elif isinstance(payload, list):
        for node in payload:
            found.extend(_iter_json_ld_objects(node))
    return found


def extract_hiring_org_from_html(markup: str) -> Optional[str]:
    """Read JobPosting.hiringOrganization from JSON-LD when boards hide the name in snippets.

    # Ref: schema.org JobPosting
    """
    for raw in re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        markup,
        flags=re.I | re.S,
    ):
        candidate = html_lib.unescape(raw).strip()
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        for node in _iter_json_ld_objects(payload):
            types = node.get("@type")
            type_list = types if isinstance(types, list) else [types]
            if "JobPosting" not in {str(item) for item in type_list if item}:
                continue
            org = node.get("hiringOrganization")
            name = None
            if isinstance(org, dict):
                name = org.get("name")
            elif isinstance(org, str):
                name = org
            if isinstance(name, str) and is_usable_company_name(name):
                return " ".join(name.split())
    labeled = _ORG_LABEL_RE.search(markup)
    if labeled:
        name = html_lib.unescape(re.sub(r"<[^>]+>", "", labeled.group(1))).strip(" \"'")
        if is_usable_company_name(name):
            return " ".join(name.split())
    return None


def extract_hiring_org_from_text(text: str) -> Optional[str]:
    """Fallback when Tavily returns markdown instead of HTML."""
    labeled = _ORG_LABEL_RE.search(text or "")
    if not labeled:
        return None
    name = labeled.group(1).strip(" \"'")
    return " ".join(name.split()) if is_usable_company_name(name) else None


def fetch_page_text(url: str) -> str:
    """Load the original listing page so JSON-LD / company fields survive snippet truncation."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; Jobhunter/0.2; "
            "+https://github.com/jobhunter-local)"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    with httpx.Client(headers=headers, timeout=20.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.text


def html_to_visible_text(html: str) -> str:
    """Strip tags for JD scoring. # Ref: pasted JobsDB ingest"""
    content = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", content).strip()


def resolve_employer_name(url: str, snippet: str = "") -> Optional[str]:
    """Best-effort legal/trade name from listing text, then the live job URL."""
    from_snippet = extract_hiring_org_from_html(snippet) or extract_hiring_org_from_text(snippet)
    if from_snippet:
        return from_snippet
    try:
        page = fetch_page_text(url)
    except httpx.HTTPError:
        return None
    return extract_hiring_org_from_html(page) or extract_hiring_org_from_text(page)


# ---------------------------------------------------------------------------
# 3. Pydantic data models
# ---------------------------------------------------------------------------

class JobFitEvaluation(BaseModel):
    """LLM structured output for a single JD vs candidate profile.

    # Ref: pipeline filter — is_valid_job / is_direct_hire / match_score
    """

    is_valid_job: bool = Field(
        description="是否為真實合法的 IT 職缺（非詐騙、非純廣告、非過期）"
    )
    is_direct_hire: bool = Field(
        description="是否為企業官方直聘（True: 直聘, False: 第三方獵頭代理）"
    )
    is_hong_kong_role: bool = Field(
        description="職缺工作地是否為香港（含 Hybrid 但需在港上班）"
    )
    company_name: str = Field(
        description=(
            "僱主法定或常用名稱。若完全無法得知則填空字串；"
            "禁止填 Not Disclosed / Unknown / Confidential / 未披露"
        )
    )
    job_title: str
    location_mode: str = Field(description="On-site / Hybrid / Remote")
    salary_range: Optional[str] = Field(
        default=None, description="薪資範圍或標註 Not Disclosed"
    )
    tech_stack_required: List[str] = Field(description="JD 要求的核心技術棧")
    match_score: int = Field(ge=0, le=100, description="0-100 技能適配度得分")
    matched_skills: List[str] = Field(description="匹配的技能")
    missing_skills: List[str] = Field(description="缺少或較弱的技能")
    recommendation_reason: str = Field(description="推薦或淘汰的關鍵依據")


# ---------------------------------------------------------------------------
# 4. SQLite + sqlite-vec
# ---------------------------------------------------------------------------

def serialize_f32(vector: List[float]) -> bytes:
    """Pack a float32 vector for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector)


class JobDBManager:
    def __init__(self, db_path: str = DEFAULT_DB_PATH, embedding_dim: int = 1536):
        self.db = sqlite3.connect(db_path)
        self.db.enable_load_extension(True)
        sqlite_vec.load(self.db)
        self.db.enable_load_extension(False)
        self.embedding_dim = embedding_dim
        self._init_tables()

    def _init_tables(self):
        with self.db:
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS job_postings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_url TEXT UNIQUE,
                    company_name TEXT,
                    job_title TEXT,
                    source_domain TEXT,
                    source_lane TEXT,
                    location_mode TEXT,
                    salary_range TEXT,
                    match_score INTEGER,
                    matched_skills TEXT,
                    missing_skills TEXT,
                    is_direct_hire BOOLEAN,
                    recommendation_reason TEXT,
                    jd_snippet TEXT,
                    created_at TEXT
                );
            """)
            self.db.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_job_postings USING vec0(
                    id INTEGER PRIMARY KEY,
                    embedding float[{self.embedding_dim}]
                );
            """)
            existing = {
                row[1]
                for row in self.db.execute("PRAGMA table_info(job_postings)").fetchall()
            }
            if "source_lane" not in existing:
                self.db.execute(
                    "ALTER TABLE job_postings ADD COLUMN source_lane TEXT"
                )
            if "created_at" not in existing:
                self.db.execute(
                    "ALTER TABLE job_postings ADD COLUMN created_at TEXT"
                )
            # Career-architect dual-score columns (agent_2). Safe on existing DBs.
            # Ref: job_postings dual-score matrix
            for column, ddl in (
                ("target_industry", "TEXT"),
                ("hard_skill_match_score", "INTEGER"),
                ("transferability_score", "INTEGER"),
                ("transferable_strengths", "TEXT"),
                ("career_advisory_note", "TEXT"),
                ("cv_status", "TEXT"),
                ("cv_pdf_path", "TEXT"),
                ("cv_typ_path", "TEXT"),
                ("cover_letter_pdf_path", "TEXT"),
                ("cover_letter_typ_path", "TEXT"),
                # Agent 4 — application readiness audit columns.
                # Ref: Agent 4 cert_matcher_agent — application_ready flag + checklist path
                ("application_ready", "BOOLEAN"),
                ("application_checklist_path", "TEXT"),
                # Agent 0 — Milo PAC snapshot per job (audit trail).
                # Ref: milo_intake_agent — acceptance_context_json for per-job PAC.
                ("acceptance_context_json", "TEXT"),
                ("expired", "BOOLEAN"),
                ("user_status", "TEXT"),
            ):
                if column not in existing:
                    self.db.execute(
                        f"ALTER TABLE job_postings ADD COLUMN {column} {ddl}"
                    )
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS company_dossiers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_name TEXT NOT NULL UNIQUE,
                    industry TEXT,
                    company_type TEXT,
                    is_legitimate_employer BOOLEAN,
                    stability_outlook TEXT,
                    confidence INTEGER,
                    dossier_json TEXT NOT NULL,
                    source_urls TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
            """)
            dossier_cols = {
                row[1]
                for row in self.db.execute("PRAGMA table_info(company_dossiers)").fetchall()
            }
            if "vetting_verdict" not in dossier_cols:
                self.db.execute(
                    "ALTER TABLE company_dossiers ADD COLUMN vetting_verdict TEXT"
                )
            if "markdown_path" not in dossier_cols:
                self.db.execute(
                    "ALTER TABLE company_dossiers ADD COLUMN markdown_path TEXT"
                )
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS research_search_cache (
                    cache_key TEXT PRIMARY KEY,
                    company_name TEXT NOT NULL,
                    raw_results_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            # Agent 0 — Milo chat history (full history stored, context compressed separately).
            # Ref: milo_intake_agent — chat history + executive_narrative compression.
            self.db.execute("""
                CREATE TABLE IF NOT EXISTS milo_chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            self._rewrite_phenom_listing_urls()

    def _rewrite_phenom_listing_urls(self) -> None:
        """Fix HKJC/HKT Phenom URLs so the dashboard link opens the vacancy."""
        try:
            rows = self.db.execute(
                "SELECT id, job_url, job_title FROM job_postings"
            ).fetchall()
        except sqlite3.OperationalError:
            return
        for job_id, url, title in rows:
            new_url = normalize_listing_url(url or "")
            new_title = display_listing_title(title or "", new_url or url or "")
            if new_url == (url or "") and new_title == (title or ""):
                continue
            try:
                self.db.execute(
                    "UPDATE job_postings SET job_url = ?, job_title = ? WHERE id = ?",
                    (new_url or url, new_title or title, job_id),
                )
            except sqlite3.IntegrityError:
                continue

    def job_exists(self, url: str) -> bool:
        cursor = self.db.execute("SELECT 1 FROM job_postings WHERE job_url = ?", (url,))
        return cursor.fetchone() is not None

    def job_id_for_url(self, url: str) -> Optional[int]:
        """Return stored posting id for this URL, if any.

        # Ref: job_postings.job_url UNIQUE — skip duplicate Rex inserts
        """
        cursor = self.db.execute(
            "SELECT id FROM job_postings WHERE job_url = ?", (url,)
        )
        row = cursor.fetchone()
        return int(row[0]) if row else None

    def list_jobs_matching_targets(
        self,
        terms: Sequence[str],
        *,
        limit: int = 8,
    ) -> List[dict]:
        """Return stored jobs whose title/industry/snippet overlap target terms.

        # Ref: Milo retrieves job_postings only after a major target shift
        """
        from target_shift import matching_job_where

        where_sql, params = matching_job_where(terms)
        if not where_sql:
            return []
        cursor = self.db.execute(
            f"""
            SELECT id, job_url, job_title, company_name, jd_snippet,
                   match_score, target_industry, transferability_score
            FROM job_postings
            WHERE {where_sql}
            ORDER BY COALESCE(match_score, 0) DESC, id DESC
            LIMIT ?
            """,
            (*params, int(limit)),
        )
        rows = []
        for row in cursor.fetchall():
            rows.append({
                "id": row[0],
                "job_url": row[1] or "",
                "job_title": row[2] or "",
                "company_name": row[3] or "",
                "jd_snippet": row[4] or "",
                "match_score": row[5],
                "target_industry": row[6] or "",
                "transferability_score": row[7],
            })
        return rows

    def save_job(self, job_data: dict, embedding: List[float]) -> int:
        strengths = job_data.get("transferable_strengths")
        if strengths is None:
            strengths = job_data.get("matched_skills") or []
        gaps = job_data.get("bridging_gaps")
        if gaps is None:
            gaps = job_data.get("missing_skills") or []
        existing_id = self.job_id_for_url(job_data["job_url"])
        if existing_id is None and job_data.get("job_url"):
            existing_id = self.job_id_for_url(normalize_listing_url(job_data["job_url"]))
        if existing_id is not None:
            return existing_id
        with self.db:
            try:
                cursor = self.db.execute("""
                INSERT INTO job_postings (
                    job_url, company_name, job_title, source_domain, source_lane,
                    location_mode, salary_range, match_score,
                    matched_skills, missing_skills, is_direct_hire,
                    recommendation_reason, jd_snippet, created_at,
                    target_industry, hard_skill_match_score, transferability_score,
                    transferable_strengths, career_advisory_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_data.get("job_url") and normalize_listing_url(job_data["job_url"]) or job_data["job_url"],
                job_data["company_name"],
                display_listing_title(job_data["job_title"] or "", job_data.get("job_url") or "")
                or job_data["job_title"],
                job_data["source_domain"], job_data["source_lane"],
                job_data["location_mode"], job_data["salary_range"],
                job_data["match_score"], json.dumps(job_data.get("matched_skills") or strengths),
                json.dumps(job_data.get("missing_skills") or gaps), job_data["is_direct_hire"],
                job_data["recommendation_reason"], job_data["jd_snippet"],
                job_data["created_at"],
                job_data.get("target_industry"),
                job_data.get("hard_skill_match_score"),
                job_data.get("transferability_score"),
                json.dumps(strengths, ensure_ascii=False),
                job_data.get("career_advisory_note"),
            ))
                row_id = cursor.lastrowid
                self.db.execute(
                    "INSERT INTO vec_job_postings (id, embedding) VALUES (?, ?)",
                    (row_id, serialize_f32(embedding)),
                )
                return row_id
            except sqlite3.IntegrityError:
                existing_id = self.job_id_for_url(job_data["job_url"])
                if existing_id is not None:
                    return existing_id
                raise

    def listing_eval_state(self, url: str) -> Optional[dict]:
        """Id, score, and eval reason for a stored posting URL.

        # Ref: System One — skip DeepSeek when already scored
        """
        for candidate in (url, normalize_listing_url(url or "")):
            if not candidate:
                continue
            cursor = self.db.execute(
                """
                SELECT id, match_score, recommendation_reason, company_name, job_title
                FROM job_postings WHERE job_url = ?
                """,
                (candidate,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "match_score": row[1],
                    "recommendation_reason": row[2] or "",
                    "company_name": row[3] or "",
                    "job_title": row[4] or "",
                }
        return None

    def update_job_evaluation(self, job_id: int, job_data: dict) -> None:
        """Fill scores after a stored JD is evaluated.

        # Ref: store-first Rex — INSERT snippet, then UPDATE fit scores
        """
        strengths = job_data.get("transferable_strengths")
        if strengths is None:
            strengths = job_data.get("matched_skills") or []
        gaps = job_data.get("bridging_gaps")
        if gaps is None:
            gaps = job_data.get("missing_skills") or []
        with self.db:
            self.db.execute(
                """
                UPDATE job_postings SET
                    company_name = ?,
                    job_title = ?,
                    location_mode = ?,
                    salary_range = ?,
                    match_score = ?,
                    matched_skills = ?,
                    missing_skills = ?,
                    is_direct_hire = ?,
                    recommendation_reason = ?,
                    jd_snippet = COALESCE(?, jd_snippet),
                    target_industry = ?,
                    hard_skill_match_score = ?,
                    transferability_score = ?,
                    transferable_strengths = ?,
                    career_advisory_note = ?
                WHERE id = ?
                """,
                (
                    job_data["company_name"],
                    display_listing_title(job_data["job_title"] or "", job_data.get("job_url") or "")
                    or job_data["job_title"],
                    job_data.get("location_mode"),
                    job_data.get("salary_range"),
                    job_data["match_score"],
                    json.dumps(job_data.get("matched_skills") or strengths),
                    json.dumps(job_data.get("missing_skills") or gaps),
                    job_data.get("is_direct_hire"),
                    job_data.get("recommendation_reason"),
                    job_data.get("jd_snippet"),
                    job_data.get("target_industry"),
                    job_data.get("hard_skill_match_score"),
                    job_data.get("transferability_score"),
                    json.dumps(strengths, ensure_ascii=False),
                    job_data.get("career_advisory_note"),
                    int(job_id),
                ),
            )

    def mark_listing_eval_skipped(self, job_id: int, reason: str) -> None:
        with self.db:
            self.db.execute(
                """
                UPDATE job_postings
                SET recommendation_reason = ?
                WHERE id = ?
                """,
                (reason[:500], int(job_id)),
            )

    def refresh_pending_jd_snippet(
        self, job_id: int, *, company_name: str, job_title: str, jd_snippet: str
    ) -> None:
        """Fill snippet on a store-first row that is not scored yet.

        # Ref: save_job returns existing id without rewriting snippet
        """
        with self.db:
            self.db.execute(
                """
                UPDATE job_postings
                SET company_name = ?,
                    job_title = ?,
                    jd_snippet = ?,
                    recommendation_reason = ?
                WHERE id = ?
                """,
                (
                    company_name,
                    job_title,
                    jd_snippet,
                    "pending_eval",
                    int(job_id),
                ),
            )

    def get_dossier_meta(self, company_name: str) -> Optional[dict]:
        """updated_at + confidence for System One Dana re-run.

        # Ref: company_dossiers.updated_at Asia/Hong_Kong
        """
        cursor = self.db.execute(
            """
            SELECT updated_at, confidence, vetting_verdict, dossier_json
            FROM company_dossiers
            WHERE LOWER(TRIM(company_name)) = LOWER(TRIM(?))
            """,
            (company_name,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "updated_at": row[0],
            "confidence": row[1],
            "vetting_verdict": row[2],
            "dossier_json": row[3],
        }

    def latest_job_created_at(self, company_name: str) -> Optional[str]:
        cursor = self.db.execute(
            """
            SELECT MAX(created_at) FROM job_postings
            WHERE LOWER(TRIM(company_name)) = LOWER(TRIM(?))
            """,
            (company_name,),
        )
        row = cursor.fetchone()
        return str(row[0]) if row and row[0] else None

    def search_similar_jobs(self, query_embedding: List[float], limit: int = 5) -> List[dict]:
        """KNN over sqlite-vec embeddings."""
        cursor = self.db.execute("""
            SELECT
                j.id, j.company_name, j.job_title, j.match_score, j.job_url, v.distance
            FROM vec_job_postings v
            JOIN job_postings j ON j.id = v.id
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
        """, (serialize_f32(query_embedding), limit))

        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0], "company": row[1], "title": row[2],
                "match_score": row[3], "url": row[4], "distance": row[5],
            })
        return results

    def list_companies_pending_diligence(
        self, min_score: int = 80, include_existing: bool = False
    ) -> List[dict]:
        """Companies whose jobs meet Dana's min composite, with no dossier yet.

        match_score in SQLite is the 55/45 composite. Transferability alone
        does not qualify.
        # Ref: due-diligence queue — composite gate + company_dossiers cache
        """
        cursor = self.db.execute(
            """
            SELECT
                j.company_name,
                MAX(j.match_score) AS best_score,
                GROUP_CONCAT(DISTINCT j.job_title) AS job_titles,
                GROUP_CONCAT(DISTINCT j.job_url) AS job_urls,
                GROUP_CONCAT(DISTINCT substr(j.jd_snippet, 1, 240)) AS jd_snippets
            FROM job_postings j
            WHERE COALESCE(j.match_score, 0) >= ?
              AND COALESCE(j.expired, 0) = 0
            GROUP BY LOWER(TRIM(j.company_name))
            ORDER BY best_score DESC
            """,
            (min_score,),
        )
        rows = []
        for name, score, titles, urls, snippets in cursor.fetchall():
            if not is_usable_company_name(name or ""):
                continue
            if not include_existing and self.has_current_dossier(name or ""):
                continue
            rows.append({
                "company_name": name,
                "best_score": score,
                "job_titles": titles or "",
                "job_urls": urls or "",
                "jd_snippets": snippets or "",
            })
        return rows

    def get_job_by_id(self, job_id: int) -> Optional[dict]:
        cursor = self.db.execute(
            """
            SELECT id, job_url, job_title, company_name, jd_snippet, match_score
            FROM job_postings
            WHERE id = ?
            """,
            (job_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "job_url": row[1],
            "job_title": row[2],
            "company_name": row[3],
            "jd_snippet": row[4] or "",
            "match_score": row[5],
        }

    def list_active_jobs_for_company(
        self,
        company_name: str,
        min_score: int = 80,
    ) -> List[dict]:
        """Live (not expired) high-score jobs for one employer.

        # Ref: Dana listing check — expire gone URLs before Tavily
        """
        cursor = self.db.execute(
            """
            SELECT id, job_url, job_title, company_name, jd_snippet, match_score
            FROM job_postings
            WHERE LOWER(TRIM(company_name)) = LOWER(TRIM(?))
              AND COALESCE(expired, 0) = 0
              AND COALESCE(match_score, 0) >= ?
            ORDER BY match_score DESC
            """,
            (company_name, min_score),
        )
        rows = []
        for job_id, url, title, company, snippet, score in cursor.fetchall():
            rows.append({
                "id": job_id,
                "job_url": url or "",
                "job_title": title or "",
                "company_name": company or "",
                "jd_snippet": snippet or "",
                "match_score": score,
            })
        return rows

    def set_job_expired(self, job_id: int, expired: bool = True) -> None:
        """Dashboard + Dana share this flag. Agents can still read the row."""
        with self.db:
            self.db.execute(
                "UPDATE job_postings SET expired = ? WHERE id = ?",
                (1 if expired else 0, int(job_id)),
            )

    def list_jobs_missing_employer(self, min_score: int = 80) -> List[dict]:
        """High-score jobs whose stored company_name is a placeholder."""
        cursor = self.db.execute(
            """
            SELECT id, job_url, job_title, company_name, jd_snippet, match_score
            FROM job_postings
            WHERE COALESCE(expired, 0) = 0
              AND COALESCE(match_score, 0) >= ?
            """,
            (min_score,),
        )
        rows = []
        for job_id, url, title, company, snippet, score in cursor.fetchall():
            if is_usable_company_name(company or ""):
                continue
            rows.append({
                "id": job_id,
                "job_url": url,
                "job_title": title,
                "company_name": company,
                "jd_snippet": snippet or "",
                "match_score": score,
            })
        return rows

    def update_job_company_name(self, job_id: int, company_name: str) -> None:
        with self.db:
            self.db.execute(
                "UPDATE job_postings SET company_name = ? WHERE id = ?",
                (company_name, job_id),
            )

    def delete_dossier(self, company_name: str) -> None:
        with self.db:
            self.db.execute(
                """
                DELETE FROM company_dossiers
                WHERE LOWER(TRIM(company_name)) = LOWER(TRIM(?))
                """,
                (company_name,),
            )
            self.db.execute(
                """
                DELETE FROM research_search_cache
                WHERE LOWER(TRIM(company_name)) = LOWER(TRIM(?))
                """,
                (company_name,),
            )

    def has_current_dossier(self, company_name: str) -> bool:
        """True when a deep-dossier JSON (vetting_verdict) already exists."""
        cursor = self.db.execute(
            """
            SELECT dossier_json FROM company_dossiers
            WHERE LOWER(TRIM(company_name)) = LOWER(TRIM(?))
            """,
            (company_name,),
        )
        row = cursor.fetchone()
        if not row:
            return False
        try:
            payload = json.loads(row[0])
        except json.JSONDecodeError:
            return False
        return isinstance(payload, dict) and "vetting_verdict" in payload

    def dossier_exists(self, company_name: str) -> bool:
        cursor = self.db.execute(
            """
            SELECT 1 FROM company_dossiers
            WHERE LOWER(TRIM(company_name)) = LOWER(TRIM(?))
            """,
            (company_name,),
        )
        return cursor.fetchone() is not None

    def get_search_cache(self, cache_key: str, max_age_days: int) -> Optional[List[dict]]:
        cursor = self.db.execute(
            """
            SELECT raw_results_json, created_at
            FROM research_search_cache
            WHERE cache_key = ?
            """,
            (cache_key,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        created = datetime.fromisoformat(row[1])
        if created.tzinfo is None:
            created = created.replace(tzinfo=HK_TZ)
        age_days = (datetime.now(HK_TZ) - created.astimezone(HK_TZ)).days
        if age_days > max_age_days:
            return None
        payload = json.loads(row[0])
        return payload if isinstance(payload, list) else None

    def save_search_cache(self, cache_key: str, company_name: str, results: List[dict]) -> None:
        with self.db:
            self.db.execute(
                """
                INSERT OR REPLACE INTO research_search_cache
                    (cache_key, company_name, raw_results_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (cache_key, company_name, json.dumps(results, ensure_ascii=False), now_hk_iso()),
            )

    # --- Milo chat history (Agent 0) ---

    def save_chat_message(self, candidate_id: str, role: str, content: str) -> None:
        """Store a single chat message for Milo's chatbot.

        # Ref: milo_intake_agent — full chat history persistence.
        """
        with self.db:
            self.db.execute(
                "INSERT INTO milo_chat_history (candidate_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (candidate_id, role, content, now_hk_iso()),
            )

    def load_chat_history(self, candidate_id: str) -> List[dict]:
        """Load all chat messages for a candidate, ordered chronologically."""
        cursor = self.db.execute(
            "SELECT role, content FROM milo_chat_history WHERE candidate_id = ? ORDER BY id",
            (candidate_id,),
        )
        return [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]

    def save_dossier(self, company_name: str, dossier: dict, markdown_path: str = "") -> int:
        payload = json.dumps(dossier, ensure_ascii=False)
        stamp = now_hk_iso()
        verdict = dossier.get("vetting_verdict")
        with self.db:
            cursor = self.db.execute(
                """
                INSERT INTO company_dossiers (
                    company_name, industry, company_type, is_legitimate_employer,
                    stability_outlook, confidence, dossier_json, source_urls,
                    vetting_verdict, markdown_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(company_name) DO UPDATE SET
                    industry = excluded.industry,
                    company_type = excluded.company_type,
                    is_legitimate_employer = excluded.is_legitimate_employer,
                    stability_outlook = excluded.stability_outlook,
                    confidence = excluded.confidence,
                    dossier_json = excluded.dossier_json,
                    source_urls = excluded.source_urls,
                    vetting_verdict = excluded.vetting_verdict,
                    markdown_path = excluded.markdown_path,
                    updated_at = excluded.updated_at
                """,
                (
                    company_name,
                    ", ".join(dossier.get("detected_tech_stack") or []) or None,
                    dossier.get("engineering_culture"),
                    str(verdict or "").upper().startswith("PROCEED"),
                    verdict,
                    dossier.get("confidence"),
                    payload,
                    json.dumps(dossier.get("source_urls") or [], ensure_ascii=False),
                    verdict,
                    markdown_path,
                    stamp,
                    stamp,
                ),
            )
            return cursor.lastrowid or 0


# ---------------------------------------------------------------------------
# 5. Talent Scout Agent
# ---------------------------------------------------------------------------

class TalentScoutAgent:
    def __init__(self, tavily_api_key: str, deepseek_api_key: str):
        self.tavily = TavilyClient(api_key=tavily_api_key)
        self.chat_model = os.environ.get("DEEPSEEK_MODEL", DEEPSEEK_CHAT_MODEL)
        self.client = instrument_openai(OpenAI(
            api_key=deepseek_api_key,
            base_url=DEEPSEEK_BASE_URL,
        ))
        self.db_manager = JobDBManager(embedding_dim=EMBEDDING_DIM)

    def get_embedding(self, text: str) -> List[float]:
        return lexical_embedding(text, EMBEDDING_DIM)

    def _tavily_search(
        self,
        query: str,
        include_domains: Sequence[str],
        max_results: int = 8,
    ) -> List[dict]:
        domains = [
            pattern.split("/", 1)[0].lower()
            for pattern in dict.fromkeys(include_domains)
        ]
        domains = list(dict.fromkeys(domains))[:TAVILY_MAX_INCLUDE_DOMAINS]
        if not domains:
            return []
        # days= is ignored unless topic=news; use time_range instead.
        # Ref: Tavily Search API time_range / include_raw_content / include_domains
        try:
            response = self.tavily.search(
                query=query,
                include_domains=domains,
                search_depth="advanced",
                max_results=max_results,
                time_range=DEFAULT_TIME_RANGE,
                include_raw_content="markdown",
            )
        except Exception as exc:
            print(f"⚠️ [Tavily search failed] {exc}")
            try:
                from activity_logger import log_activity
                log_activity("Rex", f"Tavily search failed: {exc}", level="WARN")
            except Exception:
                pass
            return []
        return response.get("results", []) or []

    def _jobsdb_postings_from_category(self, category_url: str, seed: dict) -> List[dict]:
        """Turn a JobsDB SEO index into real /job/{id} pages Rex can score.

        Tavily Search returns category URLs only; Tavily extract of those pages
        still lists relative /job/ ids. Individual /job/{id} extract usually
        fails Cloudflare, so we reuse fetch_page_text (same path as paste ingest).
        # Ref: hk.jobsdb.com Cloudflare on vacancy URLs
        """
        blob = str(seed.get("raw_content") or seed.get("content") or "")
        cards = jobsdb_postings_from_listing_text(blob, MAX_JOBSDB_POSTINGS_PER_CATEGORY)
        if len(cards) < 2:
            try:
                extracted = self.tavily.extract(urls=[category_url])
            except Exception as exc:
                print(f"⚠️ [JobsDB category extract failed] {category_url}: {exc}")
                extracted = {}
            rows = (extracted or {}).get("results") or []
            extra = ""
            if rows:
                extra = str(rows[0].get("raw_content") or rows[0].get("content") or "")
            if extra:
                cards = jobsdb_postings_from_listing_text(
                    extra, MAX_JOBSDB_POSTINGS_PER_CATEGORY
                )
        grown: List[dict] = []
        for card in cards:
            posting_url = normalize_listing_url(card.get("url") or "")
            if not posting_url or not is_job_posting_url(posting_url):
                continue
            try:
                html = fetch_page_text(posting_url)
            except Exception as exc:
                print(f"   ⏭️  [JobsDB fetch failed] {posting_url}: {exc}")
                continue
            content = html_to_visible_text(html)
            if len(content) < 80:
                print(f"   ⏭️  [JobsDB page too short] {posting_url}")
                continue
            title = (card.get("title") or "").strip() or title_from_job_url(posting_url)
            grown.append(
                {
                    "url": posting_url,
                    "title": title,
                    "content": content[:8000],
                    "raw_content": content[:20000],
                    "published_date": seed.get("published_date"),
                }
            )
        print(
            f"   ↪️  [JobsDB expanded] {category_url} → {len(grown)} posting(s)"
        )
        try:
            from activity_logger import log_activity
            log_activity(
                "Rex",
                f"JobsDB category expanded: {len(grown)} postings from {category_url}",
            )
        except Exception:
            pass
        return grown

    def _expand_jobsdb_hits(self, items: List[dict]) -> List[dict]:
        """Keep posting URLs; expand a few JobsDB category pages into vacancies."""
        posting_items: List[dict] = []
        expanded = 0
        for item in items:
            url = item.get("url") or ""
            if is_job_posting_url(url):
                posting_items.append(item)
                continue
            if (
                expanded >= MAX_JOBSDB_CATEGORY_EXPAND_PER_SEARCH
                or not is_jobsdb_category_url(url)
            ):
                continue
            grown = self._jobsdb_postings_from_category(url, item)
            if not grown:
                continue
            expanded += 1
            posting_items.extend(grown)
        return posting_items

    def _hkstp_postings_from_listing(self, listing_url: str, seed: dict) -> List[dict]:
        """Turn the HKSTP Talent Pool index into /job/{id}/{slug} vacancies.

        # Ref: https://talentjobseeker.hkstp.org/ — Tavily often returns the home index
        """
        blob = str(seed.get("raw_content") or seed.get("content") or "")
        cards = hkstp_postings_from_listing_text(blob, MAX_HKSTP_POSTINGS_PER_LISTING)
        if len(cards) < 2:
            try:
                extracted = self.tavily.extract(urls=[listing_url])
            except Exception as exc:
                print(f"⚠️ [HKSTP listing extract failed] {listing_url}: {exc}")
                extracted = {}
            rows = (extracted or {}).get("results") or []
            extra = ""
            if rows:
                extra = str(rows[0].get("raw_content") or rows[0].get("content") or "")
            if extra:
                cards = hkstp_postings_from_listing_text(
                    extra, MAX_HKSTP_POSTINGS_PER_LISTING
                )
        grown: List[dict] = []
        for card in cards:
            posting_url = normalize_listing_url(card.get("url") or "")
            if not posting_url or not is_job_posting_url(posting_url):
                continue
            try:
                html = fetch_page_text(posting_url)
            except Exception as exc:
                print(f"   ⏭️  [HKSTP fetch failed] {posting_url}: {exc}")
                continue
            content = html_to_visible_text(html)
            if len(content) < 80:
                print(f"   ⏭️  [HKSTP page too short] {posting_url}")
                continue
            title = (card.get("title") or "").strip() or title_from_job_url(posting_url)
            grown.append(
                {
                    "url": posting_url,
                    "title": title,
                    "content": content[:8000],
                    "raw_content": content[:20000],
                    "published_date": seed.get("published_date"),
                }
            )
        print(f"   ↪️  [HKSTP expanded] {listing_url} → {len(grown)} posting(s)")
        try:
            from activity_logger import log_activity
            log_activity(
                "Rex",
                f"HKSTP listing expanded: {len(grown)} postings from {listing_url}",
            )
        except Exception:
            pass
        return grown

    def _expand_hkstp_hits(self, items: List[dict]) -> List[dict]:
        """Keep HKSTP vacancy URLs; expand the Talent Pool home/index into /job ids."""
        posting_items: List[dict] = []
        expanded = 0
        for item in items:
            url = item.get("url") or ""
            if is_job_posting_url(url):
                posting_items.append(item)
                continue
            if expanded >= MAX_HKSTP_LISTING_EXPAND_PER_SEARCH or not is_hkstp_listing_url(url):
                continue
            grown = self._hkstp_postings_from_listing(url, item)
            if not grown:
                continue
            expanded += 1
            posting_items.extend(grown)
        return posting_items

    def discover_company_career_domains(self, company: str) -> List[str]:
        """Find an employer's own career host when it is not in the registry.

        Large orgs often use a unique careers.* domain. We search without a
        job-board whitelist, then keep only ATS or first-party career URLs.
        """
        print(f"🏢 [Career site discovery] {company}")
        try:
            response = self.tavily.search(
                query=(
                    f"{company} official careers OR jobs Hong Kong "
                    f"site:careers OR Workday OR Greenhouse OR SuccessFactors"
                ),
                search_depth="advanced",
                max_results=5,
                time_range="year",
            )
        except Exception as exc:
            print(f"⚠️ [Career site discovery failed] {company}: {exc}")
            return []
        hosts: List[str] = []
        for item in response.get("results", []):
            url = item.get("url") or ""
            if not looks_like_official_career_url(url, company):
                continue
            if is_trusted_job_url(url) and not is_ats_host(extract_host(url)):
                # Public board hit — not the employer's own catalogue
                continue
            host = extract_host(url)
            if host and host not in hosts:
                hosts.append(host)
        return hosts

    def search_verified_jobs(
        self,
        query: str,
        max_results_per_lane: int = 8,
        target_companies: Optional[Sequence[str]] = None,
        extra_domains: Optional[Sequence[str]] = None,
        lanes: Optional[Sequence[str]] = None,
    ) -> List[dict]:
        """Search trusted lanes separately, then optionally target-employer sites.

        Why lanes: one include_domains list mixing JobsDB with 40 career sites
        makes Tavily over-rank the big boards and miss first-party catalogues.
        """
        hk_query = f"{query} Hong Kong"
        selected_lanes = list(lanes) if lanes else list(SEARCH_LANES.keys())
        merged: Dict[str, dict] = {}

        for lane_name in selected_lanes:
            domains = SEARCH_LANES.get(lane_name, [])
            if not domains:
                continue
            print(f"🔍 [Web Search:{lane_name}] {hk_query}")
            for item in self._expand_hkstp_hits(
                self._expand_jobsdb_hits(
                    self._tavily_search(hk_query, domains, max_results_per_lane)
                )
            ):
                url = item.get("url")
                if not url or not is_trusted_job_url(url, extra_domains or ()):
                    continue
                if not is_job_posting_url(url):
                    print(f"   ⏭️  [Not a posting URL] {url}")
                    continue
                if is_academic_programme_title(item.get("title") or ""):
                    print(f"   ⏭️  [Academic programme title] {item.get('title')} {url}")
                    continue
                if not is_recently_posted(item.get("published_date"), MAX_JOB_AGE_DAYS):
                    print(f"   ⏭️  [Stale listing] {url} ({item.get('published_date', '?')})")
                    continue
                item["source_lane"] = lane_name
                merged[url] = item

        target_domains: List[str] = list(extra_domains or [])
        for company in target_companies or []:
            known = domains_for_companies([company])
            if known:
                target_domains.extend(known)
            else:
                target_domains.extend(self.discover_company_career_domains(company))
        target_domains = list(dict.fromkeys(target_domains))

        if target_domains:
            print(f"🔍 [Web Search:target_employers] {hk_query} → {target_domains}")
            for item in self._tavily_search(hk_query, target_domains, max_results_per_lane):
                url = item.get("url")
                if not url:
                    continue
                if not (
                    is_trusted_job_url(url, target_domains)
                    or looks_like_official_career_url(url)
                ):
                    continue
                if not is_job_posting_url(url):
                    print(f"   ⏭️  [Not a posting URL] {url}")
                    continue
                if is_academic_programme_title(item.get("title") or ""):
                    print(f"   ⏭️  [Academic programme title] {item.get('title')} {url}")
                    continue
                if not is_recently_posted(item.get("published_date"), MAX_JOB_AGE_DAYS):
                    print(f"   ⏭️  [Stale listing] {url} ({item.get('published_date', '?')})")
                    continue
                item["source_lane"] = "target_employer"
                merged[url] = item

        return list(merged.values())

    def evaluate_job(self, jd_text: str, user_profile: dict) -> Optional[JobFitEvaluation]:
        """LLM: authenticity + skill fit. Score gate stays outside this call.

        DeepSeek Chat Completions supports JSON mode, not OpenAI .parse().
        # Ref: DeepSeek API response_format json_object
        """
        schema = json.dumps(JobFitEvaluation.model_json_schema(), ensure_ascii=False)
        system_prompt = f"""
你是一位資深 IT 技術獵頭顧問，專注香港市場。請比對以下【求職者檔案】與【職位描述 (JD)】：
1. 檢驗職缺真實性（非詐騙、非廣告、非過期）。
2. 判斷是否香港職位（工作地香港 / Hybrid 需在港）。
3. 判斷直聘或獵頭代招。
4. 計算 0-100 適配度得分，並分析匹配與缺失的技能。
5. company_name 必須是真實僱主名稱。若 JD 隱藏僱主，填空字串，不要寫 Not Disclosed。
6. Reply with a single JSON object only (no markdown), matching this JSON Schema:
{schema}

【求職者核心檔案】:
- 核心技術棧: {', '.join(user_profile.get('skills', []))}
- 工作年資: {user_profile.get('years_of_experience')} 年
- 領域經驗: {', '.join(user_profile.get('domains', []))}
- 期望工作模式: {user_profile.get('preferred_mode', 'Any')}
"""
        response = self.client.chat.completions.create(
            model=self.chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"職位描述 (JD):\n{jd_text}"},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content
        if not raw:
            return None
        try:
            return JobFitEvaluation.model_validate_json(parse_json_payload(raw))
        except Exception as exc:
            print(f"⚠️ [JSON parse skipped] {exc}")
            return None

    def run_pipeline(
        self,
        search_keywords: str,
        user_profile: dict,
        min_score: int = 75,
        target_companies: Optional[Sequence[str]] = None,
        extra_domains: Optional[Sequence[str]] = None,
    ):
        """Scan → verify URL → score → embed → store."""
        raw_jobs = self.search_verified_jobs(
            search_keywords,
            target_companies=target_companies,
            extra_domains=extra_domains,
        )
        discovered_count = 0

        for raw in raw_jobs:
            url = raw.get("url")
            if not url or self.db_manager.job_exists(url):
                continue

            content = raw.get("raw_content") or raw.get("content") or ""
            eval_res = self.evaluate_job(content, user_profile)
            if not eval_res or not eval_res.is_valid_job:
                continue
            if not eval_res.is_hong_kong_role:
                continue
            if not passes_score_gate(eval_res.match_score, min_score):
                continue

            company_name = eval_res.company_name
            if not is_usable_company_name(company_name):
                resolved = resolve_employer_name(url, content)
                if resolved:
                    print(f"🏷️  [Employer recovered] {eval_res.job_title} → {resolved}")
                    company_name = resolved
            if not is_usable_company_name(company_name):
                print(f"⏭️  [Skip anonymous employer] {eval_res.job_title}")
                continue

            job_summary_text = (
                f"{company_name} {eval_res.job_title} "
                f"{' '.join(eval_res.tech_stack_required)}"
            )
            embedding = self.get_embedding(job_summary_text)

            job_record = {
                "job_url": url,
                "company_name": company_name,
                "job_title": eval_res.job_title,
                "source_domain": extract_host(url),
                "source_lane": raw.get("source_lane", "unknown"),
                "location_mode": eval_res.location_mode,
                "salary_range": eval_res.salary_range,
                "match_score": eval_res.match_score,
                "matched_skills": eval_res.matched_skills,
                "missing_skills": eval_res.missing_skills,
                "is_direct_hire": eval_res.is_direct_hire,
                "recommendation_reason": eval_res.recommendation_reason,
                "jd_snippet": summarize_jd(self.client, self.chat_model, content),
                "created_at": now_hk_iso(),
            }
            self.db_manager.save_job(job_record, embedding)
            discovered_count += 1
            print(
                f"🎯 [發現優質職缺] {company_name} - {eval_res.job_title} "
                f"(得分: {eval_res.match_score}) [{job_record['source_lane']}]"
            )

        print(f"\n✅ 掃描完成！新增 {discovered_count} 筆高匹配度真實職缺至 SQLite 數據庫。")


# ---------------------------------------------------------------------------
# 6. Example run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    load_dotenv(PROJECT_ROOT / ".env")
    from env_keys import deepseek_api_key, tavily_api_key
    tavily_key = tavily_api_key()
    deepseek_key = deepseek_api_key()
    if not tavily_key or not deepseek_key:
        raise SystemExit(
            "Set TAVILY_API_KEY and DEEPSEEK_API_KEY in the environment or a .env file."
        )

    sample_user_profile = {
        "skills": ["Python", "FastAPI", "PostgreSQL", "LangGraph", "Docker", "IoT Telemetry"],
        "years_of_experience": 4,
        "domains": ["Backend Infrastructure", "IoT / ConTech", "AI Agents"],
        "preferred_mode": "Hybrid or Remote",
    }

    agent = TalentScoutAgent(
        tavily_api_key=tavily_key,
        deepseek_api_key=deepseek_key,
    )

    agent.run_pipeline(
        "Senior Backend Engineer Python IoT Telemetry",
        sample_user_profile,
        min_score=80,
        # Large orgs often list only on their own portal / Workday — name them here.
        target_companies=["HSBC", "MTR", "Cathay Pacific", "CLP"],
    )

    print("\n🔍 測試 sqlite-vec 向量相似度檢索：")
    query_vector = agent.get_embedding("High throughput IoT time-series database backend")
    top_matches = agent.db_manager.search_similar_jobs(query_vector, limit=3)
    for match in top_matches:
        print(
            f" - [{match['company']}] {match['title']} | "
            f"適配分: {match['match_score']} | 向量距離: {match['distance']:.4f}"
        )
