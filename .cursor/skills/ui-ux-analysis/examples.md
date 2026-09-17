# Jobhunter UI/UX examples

Failures seen on this dashboard. Use them as the default audit targets until fixed.

## Log widget too short; long data unreadable

**Where:** `frontend/src/components/AgentLogConsole.jsx`

**What went wrong:** Unified log body was `h-[240px]`, per-agent panes `h-[200px]`, lines `font-mono text-[12px]` with `break-all`. Agent tails are long; the pane is not high enough, so users only see a stub and must hunt inside a tiny scroller. Shrinking type would make it worse.

**Pass criteria:**

- Log body height **320–420px** or `min(50vh, 420px)`
- ≥ 12 visible lines at 12–13px, `leading-5`, wrap on words
- Five agent panes: 2×3 or stacked on `md`, not five cramped columns

## Job list widget not high enough

**Where:** `frontend/src/components/PipelineKanban.jsx` — column `h-[420px] w-[280px]`

**What went wrong:** Horizontal scroll for five columns is fine; vertical window is not. Cards stack; 420px shows too few jobs. Users cannot scan the pipeline without constant scrolling inside a short well.

**Pass criteria:**

- Column height **520–640px** or `min(60vh, 640px)`
- ≥ 4–6 cards visible before inner scroll
- Column width stays ≥ 280px

## Header: too many buttons, no significant separation

**Where:** `frontend/src/components/Header.jsx`

**What went wrong:** One `flex-wrap` row mixes funnel KPIs, language, profile, Edit, New person, Talk to Milo, and Telegram. Every control is a similar `panel` pill. Metrics look like buttons; actions compete; wrapping on mid widths shuffles order.

**Pass criteria:**

- Two rows **or** one row with inset groups + `divide-x` / larger `gap`
- Group A: brand · Group B: KPIs (inset, not buttons) · Group C: context (language, profile) · Group D: primary actions (Milo, Telegram)
- At most one chromatic primary action; other actions share default chrome
- If action count > 4, overflow extras into a menu

## Report snippet (example)

```markdown
## UI/UX analysis

### Blocking
- AgentLogConsole: 200px panes hide long log lines → `h-[min(50vh,420px)]`, keep 12px, wrap words
- PipelineKanban: 420px columns hide jobs → `h-[min(60vh,640px)]`
- Header: KPIs and 6 actions in one wrap row → split metrics vs actions

### Color / icons
- Telegram `#29a9eb` only on the Telegram control
- Stop unique border colors on Edit / New / Milo / Telegram in the same strip
```
