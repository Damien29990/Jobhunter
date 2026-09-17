# Jobhunter Agent Pipeline — Frontend Reference

The pipeline is three sequential agents sharing `job_agent.db`. Each agent reads the previous agent's output and writes its own. The dashboard visualizes this flow and the gates between stages.

> **Source of truth**: `src/agents/talent_scout_agent_2.py`, `src/agents/due_diligence_agent.py`, `src/agents/cv_generator_agent.py`, and the shared `src/agents/talent_scout_agent.py`. This document mirrors the logic for the frontend.

## Pipeline at a glance

```
Agent 1: talent_scout_agent_2.py   →   job_postings (match_score, hard/transfer scores)
        │
        │  gate: match_score >= 80 OR transferability_score >= 85
        ▼
Agent 2: due_diligence_agent.py    →   company_dossiers (vetting_verdict = PROCEED | AVOID)
        │
        │  gate: match_score >= 80 AND vetting_verdict = 'PROCEED'
        ▼
Agent 3: cv_generator_agent.py    →   job_postings.cv_status = MATERIALS_GENERATED | MATERIALS_RENDERED | GENERATION_FAILED
        │                            + cv_pdf_path / cv_typ_path
        │
        │  gate: match_score >= 80 AND cv_status = 'MATERIALS_GENERATED'
        ▼
Agent 4: cert_matcher_agent.py     →   job_postings.application_ready = 1
                                    + application_checklist_path
                                    + output/{company}_{title}/Application_Checklist.md
```

> `README.md` documents Agents 1–3 only. Agent 4 (`cert_matcher_agent.py`) is active in the code and adds two columns to `job_postings`. Treat the code as authoritative.

## Agent 1 — Talent Scout (Career Path Architect)

**File**: `src/agents/talent_scout_agent_2.py`
**Inherits**: `TalentScoutAgent` from `src/agents/talent_scout_agent.py`
**Writes**: `job_postings` (+ `vec_job_postings` embeddings)

### Stages (per run)
1. `load_anonymized_profile()` — read `config/master_profile.json`, strip PII, deverticalize SSSS/ConTech terms.
2. `expand_career_horizons()` — DeepSeek proposes 3–4 `CareerSearchTrack`s across PropTech / Critical Utilities / Logistics / FinTech. `fallback_horizon_plan()` on LLM failure.
3. `search_verified_jobs()` — Tavily search split across 3 lanes: `hk_job_boards`, `ats_platforms`, `hk_employer_careers` (plus `target_employer` if `--target-companies`).
4. Dual-score evaluation — `hard_skill_match_score` + `transferability_score` → `compute_composite_match_score()` (55% hard / 45% transfer).
5. Gate: `passes_dual_score_gate()` — composite ≥ `--min-score` (default 75) **OR** transferability ≥ `PIVOT_TRANSFERABILITY_FLOOR` (85).
6. Persist passing jobs to `job_postings` + embed into `vec_job_postings`.

### CLI
```cmd
python src\agents\talent_scout_agent_2.py [--min-score 75] [--query "..."] [--profile config/master_profile.json]
```

### Constants to mirror
```python
HARD_WEIGHT = 0.55
TRANSFER_WEIGHT = 0.45
PIVOT_TRANSFERABILITY_FLOOR = 85
DEFAULT_MIN_SCORE = 75
```

## Agent 2 — Due Diligence

**File**: `src/agents/due_diligence_agent.py`
**Reads**: `job_postings` (via `list_companies_pending_diligence()`)
**Writes**: `company_dossiers`, `research_search_cache`, `output/dossiers/*.md`

### Stages (per company)
1. Candidate pool: `match_score >= 80 OR transferability_score >= 85`, skipping companies that already have a dossier (unless `--force-refresh`).
2. Multi-lane Tavily research: `news` / `sentiment` / `tech` / `general` lanes, each with curated `include_domains`. Falls back to pure official backend (Wikipedia/Wikidata/company sites) when `DUE_DILIGENCE_BACKEND=official` or no `TAVILY_API_KEY`.
3. `_deep_extract_official_sites()` — `tavily.extract` on About/Business/Investors pages.
4. `distill_dossier()` — DeepSeek compresses research into a `MAX_RESEARCH_BLOB_CHARS` blob and emits a `CompanyDueDiligence` JSON. System prompt forbids fabricating Glassdoor numbers or layoff counts.
5. JSON repair: `loads_llm_json_object()` → `json_repair` → `dump_parse_failure()` on failure.
6. Dual persistence: `save_dossier()` writes `company_dossiers`; `export_dossier_markdown()` writes `output/dossiers/{company}_Dossier.md`.
7. `repair_anonymous_jobs()` — backfills real employer names for placeholder companies via `resolve_employer_name()` / `_extract_employer_llm()`.

### Verdict normalization
`normalize_verdict()` maps any verdict string to `'PROCEED'` or `'AVOID'`. The dashboard must treat only exact `'PROCEED'` as pass; anything else is a fail. Do not substring-match.

### CLI
```cmd
python src\agents\due_diligence_agent.py [--force-refresh] [--job-id N] [--company "MTR"]
```

## Agent 3 — CV Generator

**File**: `src/agents/cv_generator_agent.py`
**Reads**: `job_postings` JOIN `company_dossiers` via `list_vetted_jobs()`
**Writes**: `job_postings.cv_status` / `cv_pdf_path` / `cv_typ_path`; `output/{company}_{job_title}/CV.typ` + `CV.pdf`

### Stages (per job)
1. Gate: `match_score >= 80 AND vetting_verdict = 'PROCEED'` (default `--min-score 80`).
2. `tailor_cv()` — DeepSeek rewrites the candidate profile for ATS alignment using **only** facts in `master_profile.json` (ground-truth enforcement, STAR method). Output validated by `TailoredCVPayload`.
3. `render_typst_source()` — Jinja2 (`StrictUndefined`) renders `templates/resume.typ.j2`; all injected text passes `typ_escape` for Typst reserved chars (`# $ * _ < > @ \ [ ]`).
4. `compile_typst_resume()` — local `typst compile` → `output/{company}_{job_title}/CV.pdf`.
5. `_update_status()`:
   - PDF success → `cv_status = 'MATERIALS_GENERATED'`, `cv_pdf_path` set.
   - Typst CLI missing → `cv_status = 'MATERIALS_RENDERED'`, only `cv_typ_path` set.
   - Failure → `cv_status = 'GENERATION_FAILED'`.

### CLI
```cmd
python src\agents\cv_generator_agent.py [--job-id N] [--company "HSBC"] [--min-score 80]
```

## Agent 4 — Certificate Matcher & Application Readiness Auditor

**File**: `src/agents/cert_matcher_agent.py`
**Reads**: `job_postings` (via `list_ready_jobs()`) + `config/master_profile.json` (credentials only)
**Writes**: `job_postings.application_ready` + `application_checklist_path`; `output/{company}_{job_title}/Application_Checklist.md`

> Not yet documented in `README.md`. Active in code.

### Stages (per job)
1. Gate: `match_score >= MIN_MATCH_SCORE` (80) **AND** `cv_status = 'MATERIALS_GENERATED'` (Agent 3 must have produced a PDF).
2. `detect_application_channel()` — deterministic pre-hint from the job URL host: Workday (`myworkdayjobs.com`), Greenhouse (`greenhouse.io`), SuccessFactors, JobsDB, CTgoodjobs, LinkedIn (`/jobs`), Lever, SmartRecruiters, or Direct Email (non-ATS host with an HR email in the JD body). Default: Company Portal.
3. `audit_job()` — DeepSeek audits the JD + URL for the application mechanism and matches the candidate's **real** credentials (ground-truth from `master_profile.json` only — no fabrication) to the role. Output validated by `ApplicationReadinessPack`.
4. `render_checklist_markdown()` → `export_checklist()` writes `output/{company}_{title}/Application_Checklist.md`.
5. `_update_status(job_id, True, checklist_path)` — sets `application_ready = 1` and `application_checklist_path` on `job_postings`.

### Output shape
`ApplicationReadinessPack` = `submission_audit` (channel, target, required/optional docs, form screening traps, special instructions) + `matched_credentials[]` + `demo_recommendation` + `final_human_action_items[]`. See [data-model.md](data-model.md) for the TS interfaces. The structured JSON is **not** persisted to the DB — only the Markdown path and the `application_ready` flag. To render the structured pack in the UI, parse the Markdown server-side in v1.

### CLI
```cmd
python src\agents\cert_matcher_agent.py [--min-score 80] [--job-id N] [--company "MTR"]
```

### Constants to mirror
```python
MIN_MATCH_SCORE = 80                       # Agent 4 gate
STATUS_GENERATED = "MATERIALS_GENERATED"   # Agent 3 prerequisite
```

## State machines (for the Runs page)

If run tracking is added, model each agent as a small FSM. Suggested states per agent run:

| Agent | States |
|-------|--------|
| Agent 1 | `queued` → `profiling` → `horizon_expansion` → `searching:{lane}` → `scoring` → `embedding` → `done` \| `failed` |
| Agent 2 | `queued` → `researching:{lane}` → `extracting` → `distilling` → `repairing_json` → `persisting` → `done` \| `failed` |
| Agent 3 | `queued` → `tailoring` → `rendering_typst` → `compiling_pdf` → `done` \| `rendered_only` \| `failed` |
| Agent 4 | `queued` → `detecting_channel` → `auditing` → `rendering_checklist` → `persisting` → `done` \| `failed` |

Stream these as typed SSE events from `/api/runs/{id}/events`. The frontend renders a per-agent card with the current state + a semantic sub-status (e.g. "Searching Tavily lane: hk_job_boards (2/3)", "Auditing application channel: Workday"). Model on the AG-UI event-stream pattern: typed events, one stream per run, frontend holds a small reducer.

## Funnel SQL (for `/api/stats/funnel`)

Compute each stage server-side using the exact constants. Return `FunnelStats`:

```sql
-- Stage 1: found
SELECT COUNT(*) FROM job_postings;

-- Stage 2: score >= 80 (Agent 1's higher gate, not the default 75)
SELECT COUNT(*) FROM job_postings WHERE match_score >= 80;

-- Stage 3: vetted PROCEED (company-level, dedupe by company_name)
SELECT COUNT(DISTINCT d.company_name)
FROM company_dossiers d
WHERE d.vetting_verdict = 'PROCEED';

-- Stage 4: CV generated (job-level, either PDF or Typst)
SELECT COUNT(*) FROM job_postings
WHERE cv_status IN ('MATERIALS_GENERATED', 'MATERIALS_RENDERED');

-- Stage 5: application ready (Agent 4 — requires a real PDF, so MATERIALS_GENERATED only)
SELECT COUNT(*) FROM job_postings
WHERE application_ready = 1;
```

> Stages 3 is company-level (Agent 2 produces one dossier per employer). Stages 4–5 are job-level (Agents 3–4 produce one CV/checklist per job). The funnel is intentionally heteromorphic — label each stage clearly in the UI ("X jobs scored ≥80", "Y companies vetted PROCEED", "Z CVs generated", "W applications ready").

## Gate constants (single source of truth)

Import from the agents module in `dashboard/api/gates.py` so the dashboard never drifts:

```python
from src.agents.talent_scout_agent import (
    PIVOT_TRANSFERABILITY_FLOOR,    # 85
    HARD_WEIGHT,                    # 0.55
    TRANSFER_WEIGHT,                # 0.45
)
from src.agents.due_diligence_agent import normalize_verdict
from src.agents.cert_matcher_agent import MIN_MATCH_SCORE as AGENT4_MIN_SCORE  # 80

# Agent 1 default gate (CLI --min-score)
AGENT1_DEFAULT_MIN_SCORE = 75

# Agent 2 candidate pool gate (list_companies_pending_diligence)
AGENT2_POOL_MIN_SCORE = 80
AGENT2_POOL_TRANSFER_FLOOR = PIVOT_TRANSFERABILITY_FLOOR  # 85

# Agent 3 final gate (list_vetted_jobs)
AGENT3_CV_MIN_SCORE = 80
AGENT3_CV_REQUIRED_VERDICT = "PROCEED"

# Agent 4 gate (list_ready_jobs)
AGENT4_MIN_SCORE = AGENT4_MIN_SCORE               # 80
AGENT4_REQUIRED_CV_STATUS = "MATERIALS_GENERATED"
```

Expose these via `GET /api/gates` so the frontend can label thresholds without hardcoding them:

```ts
// lib/types.ts
export interface Gates {
  agent1_default_min_score: number;     // 75
  agent2_pool_min_score: number;        // 80
  agent2_pool_transfer_floor: number;   // 85
  agent3_cv_min_score: number;          // 80
  agent3_cv_required_verdict: Verdict;  // 'PROCEED'
  agent4_min_score: number;             // 80
  agent4_required_cv_status: CvStatus;  // 'MATERIALS_GENERATED'
  hard_weight: number;                  // 0.55
  transfer_weight: number;              // 0.45
}
```

## Score color mapping (frontend)

Pair every color with a label — never color alone:

| Range | Color (shadcn token) | Label |
|-------|---------------------|-------|
| `match_score >= 80` | `primary` (green in default theme) | "Strong" |
| `75 <= match_score < 80` | `muted-foreground` / amber | "Borderline" |
| `match_score < 75` | `muted` | "Below gate" |
| `transferability_score >= 85` | `primary` | "Pivot eligible" |
| `vetting_verdict = 'PROCEED'` | `primary` | "Proceed" |
| `vetting_verdict = 'AVOID'` | `destructive` | "Avoid" |
| `cv_status = 'MATERIALS_GENERATED'` | `primary` | "CV ready" |
| `cv_status = 'MATERIALS_RENDERED'` | `secondary` | "Typst only" |
| `cv_status = 'GENERATION_FAILED'` | `destructive` | "Failed" |
| `application_ready = true` | `primary` | "Application ready" |
| `application_ready = false/null` | `muted` | "Pending audit" |
| `application_channel` (badge) | neutral token | channel name (Workday / Greenhouse / …) |

## What the dashboard must NOT do

- ❌ Trigger agent runs from the UI without an explicit user feature request. v1 is observe-only.
- ❌ Edit `match_score`, `vetting_verdict`, `cv_status`, or `application_ready` — these are agent outputs, not user inputs.
- ❌ Re-run the score formula in TypeScript. Read `match_score` from the DB; it is already the composite.
- ❌ Treat `vetting_verdict` containing "PROCEED" as a pass. Only exact `'PROCEED'` passes (per `normalize_verdict`).
- ❌ Show `research_search_cache.raw_results_json` on the Companies page — it is large and internal. A debug "view raw research" page is the only place to expose it.
- ❌ Fabricate `ApplicationReadinessPack` JSON in the browser. Agent 4 persists only the Markdown path + flag; parse the Markdown server-side if you need the structured pack.
