---
name: dashboard-frontend-expert
description: Build the Jobhunter UI dashboard — a monitoring and control surface for the four-agent Hong Kong IT job-hunting pipeline (talent_scout → due_diligence → cv_generator → cert_matcher). Use when creating frontend pages, components, API clients, charts, tables, or real-time views over the job_agent.db SQLite data; when scaffolding the Next.js/FastAPI dashboard; or when the user mentions the dashboard, UI, frontend, or visualizing jobs/dossiers/CVs. Covers the 2026 modern stack (Next.js 16 + React 19 + TypeScript + Tailwind v4 + shadcn/ui + Recharts + TanStack Table), the FastAPI read-only layer over SQLite + sqlite-vec, agent state machines, score gates, application-channel detection, and Asia/Hong_Kong time handling.
---

# Jobhunter Dashboard — Frontend Expert

This skill turns a frontend developer into a productive contributor to the **Jobhunter dashboard**: a local-first monitoring surface for a four-agent job-hunting pipeline that stores all state in `job_agent.db` (SQLite + `sqlite-vec`).

The backend is Python (agents in `src/agents/`). There is **no HTTP API yet** — the dashboard adds a thin read-only FastAPI layer over SQLite, then a Next.js frontend that consumes it.

> **Note**: `README.md` documents three agents, but the code has four. Agent 4 (`cert_matcher_agent.py` — Certificate Matcher & Application Readiness Auditor) is active and writes `application_ready` / `application_checklist_path` columns on `job_postings`. Treat the code as authoritative; the README is catching up.

## What you are building

A dashboard that answers five questions at a glance:

1. **What jobs has Agent 1 found?** (list, scores, source lane, industry)
2. **Which employers passed/failed vetting?** (Agent 2 dossiers, verdict, confidence)
3. **Which jobs have CVs generated?** (Agent 3 status, PDF links)
4. **Which jobs are application-ready?** (Agent 4: channel detected, checklist exported, `application_ready` flag)
5. **How is the pipeline flowing end-to-end?** (funnel: found → scored ≥80 → vetted PROCEED → CV generated → application ready)

Plus drill-downs: job detail, company dossier viewer, CV PDF preview, application checklist viewer, and (stretch) a live agent-run view.

## Mandatory stack (2026 defaults)

Do not propose alternatives unless the user asks. These are pinned because they are the current, supported, ecosystem-backed choices.

| Layer | Tool | Why |
|------|------|-----|
| Framework | **Next.js 16** (App Router, Turbopack) | Server Components, streaming, file-based routing |
| Language | **TypeScript** (strict) | End-to-end types from FastAPI → client |
| UI primitives | **shadcn/ui** (Base UI) | Copy-paste, full code ownership, accessible |
| Styling | **Tailwind CSS v4** | Utility-first, shadcn theming, tiny bundles |
| Charts | **Recharts 3** | Composable, integrates with shadcn Chart |
| Data tables | **TanStack Table v9** | Sorting, filtering, pagination, 10k+ rows |
| Dark mode | **next-themes** | System detection, instant toggle, no flash |
| Backend API | **FastAPI** + **SQLModel** (or SQLAlchemy) | Async, OpenAPI auto-docs, sits next to existing agents |
| DB | Existing **SQLite + sqlite-vec** | Read-only views over `job_agent.db` |
| Real-time (stretch) | **Server-Sent Events** via FastAPI Route | Simpler than WebSockets for one-way agent progress |
| Validation | **Pydantic v2** (backend) / **zod** (frontend) | Mirror the agents' strict-typing rule |

Node 20.9+ required (Node 18 is EOL). Python 3.11+ already in use.

## Repository layout to create

Keep the dashboard as a sibling to the existing Python code so agents stay untouched:

```
Jobhunter/
├── src/agents/                 # existing — do not modify
├── config/                    # existing
├── templates/                 # existing
├── job_agent.db               # existing — the single source of truth
├── dashboard/                 # NEW — everything below is new
│   ├── api/                   # FastAPI read-only layer
│   │   ├── main.py
│   │   ├── deps.py             # DB session, read-only pragma
│   │   ├── routes/
│   │   │   ├── jobs.py
│   │   │   ├── dossiers.py
│   │   │   ├── stats.py
│   │   │   └── runs.py          # stretch: agent run progress (SSE)
│   │   ├── models.py           # Pydantic v2 response schemas
│   │   └── requirements.txt
│   ├── web/                   # Next.js 16 app
│   │   ├── app/
│   │   │   ├── (dashboard)/layout.tsx   # sidebar + header shell
│   │   │   ├── (dashboard)/page.tsx     # overview
│   │   │   ├── jobs/page.tsx
│   │   │   ├── jobs/[id]/page.tsx
│   │   │   ├── companies/page.tsx
│   │   │   ├── companies/[name]/page.tsx
│   │   │   └── runs/page.tsx           # stretch
│   │   ├── components/
│   │   ├── lib/
│   │   │   ├── api-client.ts
│   │   │   └── types.ts
│   │   └── package.json
│   └── README.md
```

## Architecture rules (non-negotiable)

1. **Read-only by default.** The FastAPI layer opens `job_agent.db` in read-only mode (`file:...job_agent.db?mode=ro`). Agents own writes; the dashboard observes. Add a write endpoint only if the user explicitly asks for "re-run" or "approve" actions.
2. **SQLite WAL + busy timeout.** Set `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;` so the dashboard never blocks an agent write.
3. **One process, one DB.** Do not copy or sync `job_agent.db` — query it in place. The dashboard is a view, not a replica.
4. **Strict types end-to-end.** Pydantic v2 response models on the API; a generated `types.ts` (or hand-written zod schemas) on the client. No `any`. This mirrors the workspace's ConTech/IoT strict-typing rule.
5. **Asia/Hong_Kong time.** All timestamps in the DB are already `Asia/Hong_Kong` (UTC+8) ISO 8601. Display them as-is; do not re-zone to UTC on the client. Use a single `formatHK()` helper.
6. **Deterministic gates, not LLM guesses.** Score thresholds (`match_score >= 80`, `vetting_verdict = 'PROCEED'`, `transferability_score >= 85`) are pure functions — reuse the exact constants from `src/agents/talent_scout_agent.py` (`PIVOT_TRANSFERABILITY_FLOOR`, etc.) in the API layer. Never re-derive thresholds in the frontend.
7. **Server Components by default.** Layouts, lists, metric cards, and static content are RSC. Add `"use client"` only to charts, sortable tables, filters, sidebar toggle, and theme switch.
8. **Stream heavy panels.** Wrap charts and big tables in `<Suspense>` with skeletons; load the shell first.

## Dashboard pages (build in this order)

### 1. Overview (`/`)
- **Pipeline funnel**: Found jobs → Score ≥ 80 → Vetted PROCEED → CV generated → Application ready. Render as a horizontal funnel (Recharts) or 5 stat cards with deltas.
- **KPI row**: total jobs, avg composite score, PROCEED rate, CVs generated, application-ready count this week.
- **Agent status strip**: 4 cards (Agent 1/2/3/4) showing last-run row counts and timestamps. If no run-tracking table exists yet, derive "last activity" from `MAX(created_at)` / `MAX(updated_at)` per table.
- **Recent activity feed**: latest 20 rows across `job_postings` + `company_dossiers` ordered by `created_at`.

### 2. Jobs (`/jobs`)
- TanStack Table with columns: company, title, source_lane, location_mode, salary_range, hard_skill, transferability, **composite** (sorted desc), target_industry, cv_status, application_ready.
- Filters: source_lane (multi-select), target_industry, cv_status, application_ready, score range slider, search (company/title).
- Color the composite score cell: ≥80 green, 75–79 amber, <75 gray. Color `vetting_verdict`: PROCEED green, AVOID red, null muted. Color `application_ready`: true green badge "Ready", false muted "Pending".
- Export CSV button (client-side from the filtered rows).

### 3. Job detail (`/jobs/[id]`)
- Header: title, company, source_domain link, salary, location.
- Score breakdown: three bars (hard / transferability / composite) with the 55/45 weighting label.
- `matched_skills` and `missing_skills` as chip groups (parse the JSON column).
- `transferable_strengths` and `career_advisory_note` in a highlighted callout.
- Linked dossier card (if exists): verdict, confidence, link to company page.
- CV section: `cv_status` badge, links to `cv_pdf_path` / `cv_typ_path` (open in new tab; serve via a `/files/*` route that reads from `output/`).
- Application readiness section (Agent 4, if `application_ready` or `application_checklist_path` is set): detected application channel badge (Workday / Greenhouse / JobsDB / LinkedIn / Direct Email / Company Portal), link to `Application_Checklist.md`, and a rendered checklist preview (submission target, required/optional documents, form screening traps, special instructions, demo recommendation, final human action items).

### 4. Companies (`/companies`)
- Table from `company_dossiers`: company, industry, verdict, confidence, dossier updated_at, markdown_path.
- Filter by verdict (PROCEED/AVOID), sort by confidence.

### 5. Company dossier (`/companies/[name]`)
- Render the dossier: verdict banner, confidence meter, `detected_tech_stack` chips, `engineering_culture`, `glassdoor_sentiment`, `recent_news_and_events`, `architectural_trade_offs`, `red_flags` / `green_flags` as two columns, `reverse_interview_questions` as a checklist, `source_urls` as a reference list.
- Parse `dossier_json` (TEXT(JSON) column) on the API side and return a typed object — never send raw JSON to the client.
- Show the linked jobs for this company below.

### 6. Runs (stretch — `/runs`)
- Only if the user adds run tracking. Stream agent progress over SSE from a `/runs/{id}/events` route. Show a per-agent progress card with semantic status ("Searching Tavily lane hk_job_boards…", "Distilling dossier…", "Compiling Typst…", "Auditing application channel…"). Model this on the AG-UI event-stream pattern: typed events, one stream per run, frontend renders a small state machine.

## Data fetching patterns

**Server Components** fetch via a typed client:

```ts
// lib/api-client.ts
import type { Job, JobListResponse } from './types';

const BASE = process.env.DASHBOARD_API_URL ?? 'http://localhost:8000';

export async function fetchJobs(params: Record<string, string>): Promise<JobListResponse> {
  const qs = new URLSearchParams(params).toString();
  const res = await fetch(`${BASE}/api/jobs?${qs}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`jobs: ${res.status}`);
  return res.json() as Promise<JobListResponse>;
}
```

**Client Components** (charts, sortable tables) use TanStack Query for refetching and polling:

```ts
'use client';
import { useQuery } from '@tanstack/react-query';

export function useJobs(filters: JobFilters) {
  return useQuery({
    queryKey: ['jobs', filters],
    queryFn: () => fetchJobs(filters),
    refetchInterval: 15_000, // agents write async; poll cheaply
  });
}
```

Polling is fine for v1 (SQLite reads are cheap). Graduate to SSE only for the Runs page.

## FastAPI layer — minimal shape

```python
# dashboard/api/main.py
from fastapi import FastAPI
from sqlmodel import SQLModel, create_engine, Session

DB_URL = "sqlite:///file:../job_agent.db?mode=ro&uri=true"
engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

app = FastAPI(title="Jobhunter Dashboard API")

@app.on_event("startup")
def _wal():
    with engine.connect() as c:
        c.exec_driver_sql("PRAGMA journal_mode=WAL;")
        c.exec_driver_sql("PRAGMA busy_timeout=5000;")
```

Define Pydantic v2 response models that mirror the DB columns (see [data-model.md](data-model.md)). Parse JSON columns (`matched_skills`, `missing_skills`, `transferable_strengths`, `dossier_json`, `source_urls`) into typed objects before returning — the client should never parse DB JSON.

## Score & verdict constants (single source of truth)

Import these from the agents module so the dashboard never drifts:

```python
# dashboard/api/gates.py
from src.agents.talent_scout_agent import (
    PIVOT_TRANSFERABILITY_FLOOR,   # 85
    HARD_WEIGHT, TRANSFER_WEIGHT,  # 0.55, 0.45
)
from src.agents.due_diligence_agent import normalize_verdict
from src.agents.cert_matcher_agent import MIN_MATCH_SCORE as AGENT4_MIN_SCORE  # 80

CV_GATE_SCORE = 80
CV_GATE_VERDICT = "PROCEED"
```

Expose `/api/stats/funnel` that computes the five funnel stages server-side using these constants. See [agent-pipeline.md](agent-pipeline.md) for the full state machine and SQL for each gate.

## Theming & layout

- **shadcn Sidebar** with `SidebarProvider` wrapping the whole `(dashboard)` layout — required, or `SidebarTrigger`/`useSidebar` throw.
- Sidebar items: Overview, Jobs, Companies, Runs (disabled until built), Settings.
- Dark mode default (developers prefer it); `next-themes` with a `localStorage` + `before-paint` script to avoid flash.
- Responsive: `lg+` persistent sidebar; `sm` off-canvas drawer with backdrop.
- Use shadcn `DataTable` pattern for Jobs and Companies — copy the block from shadcn docs, do not hand-roll.

## Accessibility & i18n

- All interactive elements keyboard-reachable (shadcn gives this for free — don't break it).
- Score colors are **never** the only signal — always pair with a label/badge.
- The UI is English-first; the README is Traditional Chinese. If the user asks for zh-HK UI, add `next-intl` with `zh-HK` and `en` locales — do not hardcode strings.

## What NOT to do

- ❌ Do not modify `src/agents/`, `config/`, or `templates/`. The dashboard is additive.
- ❌ Do not write to `job_agent.db` from the dashboard. Read-only unless an explicit "re-run/approve" feature is requested.
- ❌ Do not re-embed or copy the DB. Query it in place.
- ❌ Do not re-derive score thresholds in TypeScript. Get them from the API.
- ❌ Do not ship `any` in shared types. Mirror Pydantic models to TS.
- ❌ Do not use WebSockets for v1. SSE or polling first; WebSockets only if bidirectional control is added.
- ❌ Do not parse `dossier_json` in the browser. Parse on the API, return typed `Dossier` objects.

## First-week build order

1. Scaffold `dashboard/web` with `create-next-app` (App Router, TS, Tailwind, ESLint). Add shadcn/ui, next-themes, TanStack Table, Recharts, TanStack Query.
2. Scaffold `dashboard/api` with FastAPI + SQLModel. Wire read-only engine + WAL. Add `/api/health`.
3. Generate TS types from the FastAPI OpenAPI spec (`openapi-typescript`) into `lib/types.ts`.
4. Build the shell: `(dashboard)/layout.tsx` with sidebar + header + theme toggle.
5. Build Overview page with the funnel + KPI row (mock data first, then wire API).
6. Build Jobs table (TanStack Table + filters) → Job detail.
7. Build Companies table → Company dossier viewer (with `dossier_json` parsed to typed `Dossier`).
8. Add CSV export and PDF/TYP file serving.
9. Add Application Readiness section to Job detail (Agent 4: channel badge + checklist viewer).
10. (Stretch) Add Runs page with SSE.

## References

- [data-model.md](data-model.md) — full SQLite schema, JSON column shapes, and the typed TS interfaces to mirror.
- [agent-pipeline.md](agent-pipeline.md) — the four agents' state machines, score gates, and the SQL for each funnel stage.
- Project root `README.md` — the authoritative description of the agents and DB (note: documents Agents 1–3 only; Agent 4 lives in code).
