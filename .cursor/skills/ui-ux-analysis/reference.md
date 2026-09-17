# UI/UX analysis — reference

Token and density numbers for Jobhunter’s pixel-office dashboard. Use these as **floors**, not as a second design system.

## Type scale

| Role | Size | Line height | Notes |
|------|------|-------------|--------|
| Pixel heading | 12–14px | tight | `font-pixel` — labels only |
| KPI value | 14px | tight | one number |
| Data (logs, jobs, forms) | **12–13px** | 1.4–1.6 | never 10px for log bodies |
| Meta / hint | 11px | normal | timestamps, column hints |
| Legal / footer | 11px | normal | non-critical |

Log lines use `font-mono`. Job titles may use sans. Do not mix three sizes inside one log line.

## Color tokens (existing)

From `frontend/tailwind.config.js` and `index.css`:

| Token | Hex | Use |
|-------|-----|-----|
| ink-900 panel | `#0b1120` | chrome |
| ink-800 inset | `#0f172a` | wells |
| ink-700 border | `#1e293b` | default border |
| amber-retro | `#f59e0b` | brand / system |
| emerald-retro | `#10b981` | proceed / working |
| cyan-retro | `#06b6d4` | vetting / edit |
| rose-retro | `#f43f5e` | fail / ready / Clara |
| Telegram | `#29a9eb` | **only** the Telegram control |
| Milo | `#a78bfa` | **only** Milo |

Muted text: `#64748b` labels, `#475569` timestamps, `#94a3b8` neutral log body.

## Icon sizes

| Context | Size |
|---------|------|
| Header action | 16–18px |
| KPI | 16px |
| Inline in a row | 14–16px |
| Decorative only | avoid |

## Viewport budgets (1440×900 class)

Header + office + kanban + logs share one scroll. Typical split:

- Header band: ≤ 96px (two rows OK; one cramped row is not)
- Pixel office: content-sized, not a second page
- Job kanban: **≥ 50vh** or 520px columns
- Logs: **≥ 36vh** or 320px body

On laptop height, **cut office chrome** or collapse logs before shrinking type.

## Scroll panes

Required: `min-h-0`, `overflow-y-auto`, `kanban-scroll`, a **min visible height** in `px` or `vh`.

Anti-patterns:

- `min-h-[160px]` with no max — page grows, still feels empty then jumps
- `h-[200px]` log — ~8 lines at 12px; unusable for agent tails
- `h-[420px]` job column when cards are ~88px — only ~4 cards, borderline; prefer 520–640px
