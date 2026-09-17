# Jobhunter Data Model — Frontend Reference

The single source of truth is `job_agent.db` (SQLite) with a `sqlite-vec` virtual table for KNN search. All timestamps are `Asia/Hong_Kong` (UTC+8) ISO 8601 strings. JSON columns are stored as `TEXT` and must be parsed on the API side into typed objects before reaching the client.

> **Source of the schema**: `JobDBManager._init_tables()` in `src/agents/talent_scout_agent.py`. The agent code is authoritative; this document mirrors it for the frontend. If they ever disagree, the agent code wins.

## Tables

### `job_postings` — main job table

| Column | SQLite type | TS type | Notes |
|--------|-----------|---------|-------|
| `id` | INTEGER PK | `number` | auto-increment |
| `job_url` | TEXT UNIQUE | `string` | dedup key |
| `company_name` | TEXT | `string \| null` | may be a placeholder until Agent 2 backfills |
| `job_title` | TEXT | `string` | |
| `source_domain` | TEXT | `string \| null` | host |
| `source_lane` | TEXT | `'hk_job_boards' \| 'ats_platforms' \| 'hk_employer_careers' \| 'target_employer'` | |
| `location_mode` | TEXT | `'On-site' \| 'Hybrid' \| 'Remote' \| null` | |
| `salary_range` | TEXT | `string \| null` | free text or "Not Disclosed" |
| `match_score` | INTEGER | `number \| null` | composite (Agent 1 v2) |
| `matched_skills` | TEXT(JSON) | `string[]` | parse on API |
| `missing_skills` | TEXT(JSON) | `string[]` | parse on API |
| `is_direct_hire` | BOOLEAN | `boolean \| null` | |
| `recommendation_reason` | TEXT | `string \| null` | |
| `jd_snippet` | TEXT | `string \| null` | first ~500 chars |
| `created_at` | TEXT | `string` | Asia/Hong_Kong ISO 8601 |
| `target_industry` | TEXT | `'ConTech' \| 'PropTech' \| 'Critical Utilities' \| 'Logistics' \| 'FinTech' \| null` | |
| `hard_skill_match_score` | INTEGER | `number \| null` | 0–100 |
| `transferability_score` | INTEGER | `number \| null` | 0–100 |
| `transferable_strengths` | TEXT(JSON) | `string[]` | why the candidate's experience fits |
| `career_advisory_note` | TEXT | `string \| null` | pivot strategy |
| `cv_status` | TEXT | `'MATERIALS_GENERATED' \| 'MATERIALS_RENDERED' \| 'GENERATION_FAILED' \| null` | |
| `cv_pdf_path` | TEXT | `string \| null` | path under `output/` |
| `cv_typ_path` | TEXT | `string \| null` | path under `output/` |
| `application_ready` | BOOLEAN | `boolean \| null` | Agent 4 — set when checklist exported |
| `application_checklist_path` | TEXT | `string \| null` | Agent 4 — `output/{company}_{title}/Application_Checklist.md` |

> The last two columns are added by Agent 4 (`cert_matcher_agent.py`) and are not yet documented in `README.md`. The shared `JobDBManager._init_tables()` adds them via `ALTER TABLE ADD COLUMN` on existing DBs.

**Composite score formula** (pure function, do not re-derive in TS):
`composite = round(hard_skill_match_score * 0.55 + transferability_score * 0.45)`

### `vec_job_postings` — vector index (virtual table)

```sql
CREATE VIRTUAL TABLE vec_job_postings USING vec0(
    id INTEGER PRIMARY KEY,
    embedding float[1536]
);
```

The dashboard does **not** query this directly. Similar-job search is an API concern (`/api/jobs/{id}/similar`) that calls `JobDBManager.search_similar_jobs()`. Embedding backend is lexical feature-hashing by default, or `fastembed` (`BAAI/bge-small-en-v1.5`) if `EMBEDDING_BACKEND=fastembed`.

### `company_dossiers` — employer background reports

| Column | SQLite type | TS type | Notes |
|--------|-----------|---------|-------|
| `id` | INTEGER PK | `number` | |
| `company_name` | TEXT UNIQUE | `string` | dedup key |
| `industry` | TEXT | `string \| null` | detected tech stack summary |
| `company_type` | TEXT | `string \| null` | engineering culture summary |
| `is_legitimate_employer` | BOOLEAN | `boolean \| null` | verdict starts with PROCEED |
| `stability_outlook` | TEXT | `string \| null` | raw `vetting_verdict` |
| `confidence` | INTEGER | `number \| null` | 0–100 |
| `dossier_json` | TEXT(JSON) | `Dossier` (see below) | **parse on API** |
| `source_urls` | TEXT(JSON) | `string[]` | parse on API |
| `vetting_verdict` | TEXT | `'PROCEED' \| 'AVOID' \| null` | Agent 3 gate |
| `markdown_path` | TEXT | `string \| null` | `output/dossiers/*.md` |
| `created_at` | TEXT | `string` | Asia/Hong_Kong ISO 8601 |
| `updated_at` | TEXT | `string` | Asia/Hong_Kong ISO 8601 |

#### `Dossier` shape (parsed from `dossier_json`)

This is the `CompanyDueDiligence` Pydantic model distilled by DeepSeek in Agent 2. Mirror it exactly:

```ts
// lib/types.ts
export interface Dossier {
  vetting_verdict: 'PROCEED' | 'AVOID';
  detected_tech_stack: string[];
  engineering_culture: string;
  glassdoor_sentiment: string;        // may be "sector inference" if no Glassdoor data
  recent_news_and_events: string;
  architectural_trade_offs: string;
  red_flags: string[];
  green_flags: string[];
  reverse_interview_questions: string[];
  source_urls: string[];
  confidence: number;                   // 0–100
}
```

> Agent 2's system prompt forbids fabricating Glassdoor numbers or layoff counts. Treat `glassdoor_sentiment` as qualitative, not quantitative. Do not render it as a star rating.

### `research_search_cache` — Tavily/official search cache

| Column | SQLite type | TS type | Notes |
|--------|-----------|---------|-------|
| `cache_key` | TEXT PK | `string` | `sha256("dd_v5\|{backend}\|{normalized_company}")` |
| `company_name` | TEXT | `string` | |
| `raw_results_json` | TEXT(JSON) | `unknown` | large; do not send to client by default |
| `created_at` | TEXT | `string` | Asia/Hong_Kong ISO 8601 |

**Cache TTL**: `SEARCH_CACHE_MAX_AGE_DAYS = 14`. The dashboard's Companies page can show a "last researched" badge computed from `created_at`; do not expose `raw_results_json` unless a "view raw research" debug page is requested.

## TypeScript interfaces to generate

Use `openapi-typescript` against the FastAPI `/openapi.json` so these stay in sync. Hand-written fallback:

```ts
// lib/types.ts
export type SourceLane = 'hk_job_boards' | 'ats_platforms' | 'hk_employer_careers' | 'target_employer';
export type TargetIndustry = 'ConTech' | 'PropTech' | 'Critical Utilities' | 'Logistics' | 'FinTech';
export type CvStatus = 'MATERIALS_GENERATED' | 'MATERIALS_RENDERED' | 'GENERATION_FAILED';
export type Verdict = 'PROCEED' | 'AVOID';

export interface Job {
  id: number;
  job_url: string;
  company_name: string | null;
  job_title: string;
  source_domain: string | null;
  source_lane: SourceLane;
  location_mode: 'On-site' | 'Hybrid' | 'Remote' | null;
  salary_range: string | null;
  match_score: number | null;          // composite
  hard_skill_match_score: number | null;
  transferability_score: number | null;
  matched_skills: string[];
  missing_skills: string[];
  transferable_strengths: string[];
  is_direct_hire: boolean | null;
  recommendation_reason: string | null;
  jd_snippet: string | null;
  target_industry: TargetIndustry | null;
  career_advisory_note: string | null;
  cv_status: CvStatus | null;
  cv_pdf_path: string | null;
  cv_typ_path: string | null;
  application_ready: boolean | null;            // Agent 4
  application_checklist_path: string | null;   // Agent 4
  created_at: string;                  // Asia/Hong_Kong ISO 8601 — display as-is
}

export interface CompanyDossier {
  id: number;
  company_name: string;
  industry: string | null;
  company_type: string | null;
  is_legitimate_employer: boolean | null;
  stability_outlook: string | null;
  vetting_verdict: Verdict | null;
  confidence: number | null;
  dossier: Dossier;                    // parsed from dossier_json
  source_urls: string[];
  markdown_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobListResponse {
  items: Job[];
  total: number;
  page: number;
  page_size: number;
}

export interface FunnelStats {
  found: number;
  score_ge_80: number;
  vetted_proceed: number;
  cv_generated: number;
  application_ready: number;
}

// --- Agent 4 — Certificate Matcher & Application Readiness Auditor ---
// The checklist Markdown lives at output/{company}_{title}/Application_Checklist.md.
// The structured pack is NOT stored in the DB (only the path + application_ready flag).
// To render the structured pack in the UI, either (a) parse the Markdown server-side,
// or (b) re-run the audit and cache the JSON. v1: just link to the Markdown file.

export type ApplicationChannel =
  | 'Workday' | 'Greenhouse' | 'SuccessFactors' | 'JobsDB' | 'CTgoodjobs'
  | 'LinkedIn' | 'Lever' | 'SmartRecruiters' | 'Direct Email' | 'Company Portal';

export interface MatchedCredential {
  credential_name: string;
  category: 'Cloud' | 'Safety' | 'Language' | 'Degree' | string;
  relevance_to_role: string;
  recommended_action: string;   // "Attach PDF" / "Mention in CV header" / "State in online form field"
}

export interface PortalSubmissionAudit {
  application_channel: ApplicationChannel;
  submission_target: string;     // direct URL or HR email
  required_documents: string[];
  optional_documents: string[];
  form_screening_traps: string[]; // Expected Salary, Notice Period, Visa/HK PR status, ...
  special_submission_instructions: string;
}

export interface ApplicationReadinessPack {
  company_name: string;
  job_title: string;
  job_url: string;
  submission_audit: PortalSubmissionAudit;
  matched_credentials: MatchedCredential[];
  demo_recommendation: string | null;
  final_human_action_items: string[];
}
```

## API route sketch (FastAPI)

```python
# dashboard/api/routes/jobs.py
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, func
from .deps import get_session
from ..models import JobOut, JobListResponse
from ...src.agents.talent_scout_agent import JobDBManager  # reuse where sensible

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

@router.get("", response_model=JobListResponse)
def list_jobs(
    session: Session = Depends(get_session),
    min_score: int | None = None,
    source_lane: list[str] | None = Query(default=None),
    target_industry: list[str] | None = Query(default=None),
    cv_status: list[str] | None = Query(default=None),
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
):
    # build statement, parse JSON columns into JobOut, return
    ...
```

Parse JSON columns with a Pydantic v2 validator (`field_validator` with `mode='before'` accepting `str | list`) so the client always receives typed arrays.

## Time handling

- DB stores `Asia/Hong_Kong` ISO 8601 (e.g. `2026-09-06T22:36:00+08:00`).
- Do **not** convert to UTC on the API.
- Client helper:

```ts
// lib/time.ts
export function formatHK(iso: string, opts?: Intl.DateTimeFormatOptions): string {
  return new Date(iso).toLocaleString('zh-HK', {
    timeZone: 'Asia/Hong_Kong',
    ...opts,
  });
}

export function formatHKDate(iso: string): string {
  return formatHK(iso, { year: 'numeric', month: 'short', day: 'numeric' });
}

export function formatHKTime(iso: string): string {
  return formatHK(iso, { hour: '2-digit', minute: '2-digit', hour12: false });
}

export function relativeFromHK(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.round(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return `${days}d ago`;
}
```
