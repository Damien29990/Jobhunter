# Jobhunter Pixel Office Dashboard

A retro 16-bit pixel-art office dashboard that visualizes the four-agent job-hunting pipeline (Rex → Dana → Leo → Clara), teaches you how to operate each agent, and shows real-time job and company-dossier intelligence from `job_agent.db`.

```
┌────────────────────────────────────────────────────────┐
│ Frontend: Vite + React + Tailwind + Lucide (frontend/)  │
│  • Pixel Office · Tutorial · Quest Bar · Kanban · Drawer│
└───────────────────────┬────────────────────────────────┘
                        │ REST + subprocess spawning
┌───────────────────────▼────────────────────────────────┐
│ Backend: FastAPI (src/api/server.py)                   │
│  • read-only over job_agent.db · spawns agents         │
└───────────────────────┬────────────────────────────────┘
                        │ queries in place
                  job_agent.db (SQLite + sqlite-vec)
```

## Quick start (Windows)

```cmd
run_dashboard.bat
```

This activates the `jobhunter` conda env, installs backend + frontend deps on first run, then launches:

- **FastAPI** at `http://127.0.0.1:8000` (API docs at `/docs`)
- **Vite** at `http://127.0.0.1:5173` (proxies `/api` to the backend)

Open `http://localhost:5173`.

### Manual start (most reliable, `npm run dev`)

```cmd
:: Terminal 1 — backend API (read-only over job_agent.db)
conda activate jobhunter
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8000 --reload

:: Terminal 2 — frontend UI
cd frontend
npm install      :: first time only
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to `:8000`, so the two can run separately.

> ⚠️ **`npm run dev` alone shows no data.** It starts only the frontend; API calls need the FastAPI backend running on `:8000` at the same time. Open both terminals.

## What you see

- **Header** — funnel KPIs (Found · Score≥80 · PROCEED · CVs · Ready) + candidate profile switcher + **language switcher (English / 繁體中文)**.
- **Pixel Office** — 4 interactive 16-bit agent desks (Rex/Dana/Leo/Clara) with IDLE/WORKING/FAILED states, polled live. Click a desk to open the tutorial.
- **Quest Bar** — gamified pipeline checklist; each step lights up as its agent produces output.
- **Pipeline Kanban** — Discovered → Vetting → Vetted → Materials Ready → Applied/Archived.
- **Detail Drawer** — Overview · Dossier · Application Pack · CV Previewer tabs, plus a one-click link to the original posting.
- **Backend-offline banner** — if FastAPI isn't running on `:8000`, a red banner shows the exact start command (the most common cause of "clicking an agent does nothing").

## i18n (English + 繁體中文)

Built with `i18next` + `react-i18next`. Default = browser language (`zh*` → zh-HK, else English); choice persisted in `localStorage`. A `EN / 繁` toggle sits in the header. Translation files live in `src/lib/locales/en.json` and `zh-HK.json` — keep both in sync when adding strings. Init in `src/lib/i18n.js`; loaded in `src/main.jsx`.

## Troubleshooting

- **Clicking an agent / RUN does nothing** → the backend isn't running. The red banner at the top shows the start command.
- **`uvicorn` crashes at startup** → fixed. `src/api/gates.py` no longer imports the heavy agent modules (which pull in `openai` / `tavily` / `sqlite_vec`); it's now self-contained pure functions, so the API starts with just `fastapi` / `uvicorn` / `pydantic`.
- **`npm run dev` alone shows no data** → it starts only the frontend; API calls need FastAPI on `:8000`. Open both terminals.
- **`run_dashboard.bat` silent** → fixed. It now echoes each step, tries 3 conda activation methods, and `pause`s on error instead of closing.

## API surface (`src/api/server.py`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | DB + counts |
| GET | `/api/candidates` | candidate profiles |
| GET | `/api/jobs` | filtered job list |
| GET | `/api/jobs/{id}` | job detail |
| GET | `/api/jobs/{id}/cv` | CV PDF / `.typ` (FileResponse) |
| GET | `/api/jobs/{id}/checklist` | `Application_Checklist.md` (HTML) |
| GET | `/api/jobs/{id}/dossier` | linked company dossier |
| GET | `/api/dossiers` | all company dossiers |
| GET | `/api/dossiers/{name}` | one dossier (parsed JSON) |
| GET | `/api/dossiers/{name}/markdown` | dossier Markdown (HTML) |
| POST | `/api/agents/scout\|diligence\|cv\|assembler/run` | spawn an agent |
| POST | `/api/agents/{key}/stop` | stop a running agent |
| GET | `/api/agents/status` | per-agent IDLE/WORKING/FAILED |
| GET | `/api/stats/funnel` | 5-stage funnel counts |
| GET | `/api/gates` | threshold constants (single source of truth) |

## Architecture rules (enforced)

1. **Read-only by default.** The API opens `job_agent.db` in `mode=ro`. The dashboard never writes — agents own writes.
2. **SQLite WAL + busy_timeout=5000** so the dashboard never blocks an agent.
3. **Strict types end-to-end.** Pydantic v2 response models; JSON columns parsed on the API, never in the browser.
4. **Deterministic gates.** Thresholds are imported from the agent modules (`gates.py`) — never re-derived in the frontend.
5. **Asia/Hong_Kong time.** Timestamps displayed as-is; single `formatHK()` helper.
6. **Offline-safe pixel art.** Agents are pure SVG `<rect>` primitives — no external sprite CDNs.

## ⚠️ Multi-user: current reality vs. spec

The UI spec describes a **multi-candidate** system (`config/profiles/`, `--candidate-id` args, `candidate_job_evaluations` / `candidate_materials` tables, `output/users/{id}/` paths). **The codebase is currently single-user:**

- One profile: `config/master_profile.json`
- Shared tables: `job_postings`, `company_dossiers`, `research_search_cache`
- Only Agent 1 (Rex) accepts a `--profile` arg; Agents 2–4 have no profile concept
- Output lives at `output/{company}_{job_title}/`, not `output/users/{id}/`

The dashboard is **forward-compatible**, not fake:

- `GET /api/candidates` lists `config/profiles/*.json` if that dir exists, else falls back to `master_profile.json` as a single "default" profile.
- `POST /api/agents/scout/run` passes `--profile` to Rex when a per-profile file exists.
- The `candidate_id` param is accepted by `/api/jobs` and the run endpoints but currently scopes nothing in the shared `job_postings` table.

To make the profile switcher fully functional, the agents need a multi-user refactor (per-candidate DB tables + `--candidate-id` on Agents 2–4 + per-user output dirs). That is a separate migration — the dashboard UI is ready for it.

## Files added

```
src/api/
├── server.py          # FastAPI app + all routes
├── models.py          # Pydantic v2 response models (no Any)
├── gates.py           # thresholds imported from agents
├── agent_runner.py    # subprocess manager + status tracking
├── mdrender.py        # tiny offline markdown→HTML
└── requirements.txt
frontend/
├── package.json · vite.config.js · tailwind.config.js · postcss.config.js
├── index.html
└── src/
    ├── main.jsx · App.jsx · index.css
    ├── lib/ (api.js, agents.js)
    └── components/ (Header, ProfileSwitcher, QuestBar, PipelineKanban,
                     JobCard, DetailDrawer, TutorialModal, PixelOffice/)
run_dashboard.bat
```

The existing `src/agents/`, `config/`, and `templates/` are untouched.
