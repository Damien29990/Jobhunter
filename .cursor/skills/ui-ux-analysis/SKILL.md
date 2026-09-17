---
name: ui-ux-analysis
description: Audits dashboard and web UI for widget size (height and width), information density, typography vs long data, color, icon meaning, and visual hierarchy. Use when reviewing UI/UX, layout, headers, toolbars, log consoles, job lists, kanban columns, or when widgets feel cramped, buttons are crowded without separation, or log/list data is hard to read.
---

# UI/UX Analysis

Audit **what is on screen**, not the component tree. Judge whether a real user can scan, read, and click without fighting the layout.

Primary lenses (always cover all four):

1. **Widget size** — height and width vs content
2. **Typography** — font size vs line length
3. **Color and icons** — meaning, contrast, uniqueness
4. **Visual hierarchy** — grouping and separation of controls

Do not ship a layout change without this pass. Pair with `dashboard-frontend-expert` for stack/data rules and `frontend-animator` for motion; this skill owns **fit, read, and group**.

## When to run

- New or resized widgets (logs, lists, kanban, drawers, headers)
- User says cramped, hard to read, too many buttons, weird header
- After adding a header action (chat, Telegram, profile, language)

## Workflow

1. Identify each **region**: header, KPI strip, primary workspace, list/log, drawer/modal.
2. For each region, score **size → type → color/icon → grouping**.
3. Write findings in the [report format](#report-format). Severity first.
4. Fix only if the user asked to implement; otherwise report and recommend.

Copy this checklist:

```
UI/UX:
- [ ] Size: each scroll pane shows enough rows at a readable type size
- [ ] Type: data font ≥ 12px; long lines wrap or truncate with a title/tooltip
- [ ] Color: semantic, not a rainbow of equally loud accents
- [ ] Icons: unique meaning; 16–20px for actions; label if ambiguous
- [ ] Header: identity | metrics | actions are separated (not one wrap row)
```

## Size (height and width)

A widget that **scrolls** must still show a useful window of content. Scrollbars are not a substitute for height.

| Surface | Minimum visible content | Typical min height |
|---------|-------------------------|--------------------|
| Agent / unified **log** | 12–16 lines | **320–420px** body (not 160–240px) |
| **Job list** / kanban column | 4–6 cards | **520–640px** column (not ~420px) |
| Chat transcript | 6–8 bubbles | flex-1 in a full-height drawer |
| Header | one row of identity **or** wrap to two rows | do not pack KPIs + 6 actions in one wrap |

Rules:

- `min-h-*` without `max-h-*` / fixed height **grows the page**; `h-*` too small **clips data**. Prefer `h-[min(60vh,640px)]` (or similar) for logs and job columns.
- Width: kanban cards ≥ 280px; log panes must not force `break-all` on 12px mono as the only overflow strategy.
- If five log panes share a row, **drop columns** (2 then 1) before shrinking height or font.

## Typography vs long data

Long log lines and job titles fail when the box is short **and** the font is small.

- Body / log / list data: **≥ 12px**. Pixel titles can stay 11–13px.
- Logs: `leading-relaxed` or `leading-5`, wrap on spaces (`break-words`), keep timestamps dim and compact. Do not rely on `text-[10px]` + `break-all`.
- Prefer **more height** over smaller type. Shrinking type to fit a 200px log is a fail.
- Truncate only with `title` or a detail drawer; never clip the only copy of an error.

## Color and icons

- **Semantic color**: error `#f43f5e`, warn/system `#fbbf24`, success `#10b981`, idle `#64748b`. Agent accents (Milo violet, Rex emerald, …) are for **that agent**, not every button.
- Do not give each header button a different border color. Actions in one group share chrome; **one** primary (e.g. Talk to Milo).
- Icons: Lucide (or existing SVG) at **16–20px** for header actions. Same metaphor = same action. Telegram stays the Telegram mark; chat is `MessageSquare`.
- Color is never the only signal — keep a label or `title`.

## Header grouping (separation)

A header that is **one `flex-wrap` of KPIs + language + profile + edit + new + chat + Telegram** has no hierarchy. Split into bands:

```
Row 1: brand/title          |  primary actions (Talk to Milo, Telegram)
Row 2: funnel KPIs          |  context (language, profile, edit, new person)
```

Or one row with **visible separators**: `divide-x` / inset groups / `gap` large enough that KPIs ≠ buttons.

- **Metrics** (found / score / proceed / CVs / ready) are not buttons — keep them visually quieter (`panel-inset`).
- **Destructive or rare** (new person) must not sit equal to daily actions.
- If actions exceed four, overflow into a menu. Do not keep adding same-size pills.

## Report format

```markdown
## UI/UX analysis

### Blocking
- [widget] problem → recommended height/width/type/group

### Size
- …

### Type / long data
- …

### Color / icons
- …

### Hierarchy / header
- …

### Suggested CSS/layout
- concrete class or structure (e.g. log body `h-[min(50vh,420px)]`, header two rows)
```

## Additional resources

- Size budgets, type scale, and color tokens: [reference.md](reference.md)
- Jobhunter header / log / job-list failures: [examples.md](examples.md)
