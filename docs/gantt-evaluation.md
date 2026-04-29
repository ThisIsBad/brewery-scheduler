# Gantt component evaluation

**Status**: Decision recorded. Implementation lands in PR 2 (frontend tranche).

## Goal

Pick a Gantt/timeline component for the brewery scheduler frontend (Phase 1 onwards). The component is **the** core UX — drag-and-drop scheduling defines whether the brewmaster will adopt the tool. Constraints from Stefan:

> *"Mein Ziel ist, dass das Ganze mit möglichst wenig Ressourcen laufen kann."*

We optimize for low resource use first, then for fit.

## What "low resource" means here

| Dimension | Why it matters |
| --- | --- |
| **Frontend bundle size** | Loaded by every brewmaster on every visit; large bundles slow first paint and waste bandwidth. |
| **Runtime memory / DOM nodes** | The Gantt has up to 21 tank rows × ~100 visible Süde at peak (Pentecost). 2k–5k nodes is realistic. |
| **License cost** | Commercial Gantts (DHTMLX Pro, Bryntum) start around €700–€1500/developer-year. Free for v1. |
| **Backend cost** | All candidates render client-side, so backend impact is zero. Not a differentiator. |
| **Operational cost** | Self-hosted JS, no external services, no per-seat fees. All candidates qualify. |

## Candidates

### 1. frappe-gantt (open source, MIT)

- **Bundle**: ~30 KB minified, no React wrapper required (drop into a `<svg>` container).
- **Drag-and-drop**: bar drag + resize built-in. Vertical reassignment to a different row is *not* native — bars are bound to their task row.
- **Dependencies**: zero.
- **Maintenance**: actively maintained but slow release cadence; ~5k stars.
- **Fit**: good for read-mostly Gantts. **Risk**: row-swapping (assigning a Sud to a different tank by dragging vertically) likely needs manual extension.

### 2. react-calendar-timeline (open source, MIT)

- **Bundle**: ~70 KB minified + React wrapper. Includes time-axis pan/zoom and per-row drag.
- **Drag-and-drop**: items can be dragged horizontally (time) **and vertically across rows** out of the box. This is the exact gesture the brewmaster needs ("move this Sud from F-30-1 to F-30-2 on Wednesday").
- **Dependencies**: React, moment (legacy — newer fork uses dayjs).
- **Maintenance**: 2.5k stars; pace has slowed but still receives bug fixes; widely used.
- **Fit**: best alignment with the "tanks-as-rows, drag-Süde-between-rows" gesture.

### 3. DHTMLX Gantt (commercial / GPL dual-license)

- **Bundle**: ~250 KB.
- **Drag-and-drop**: full-featured, polished.
- **License**: GPL for the free tier, commercial license for proprietary use (~€700/dev/year).
- **Fit**: too heavy and the GPL tier is incompatible with closed-source distribution. Skip unless Stefan explicitly OKs the license cost later.

### 4. Bryntum Scheduler (commercial)

- **Bundle**: ~400+ KB.
- **License**: from ~€1500/dev/year.
- **Fit**: best-in-class UX, way out of "minimal resource" budget for v1. Skip.

### 5. vis-timeline (open source, Apache-2.0)

- **Bundle**: ~140 KB minified.
- **Drag-and-drop**: items are draggable across rows ("groups").
- **Maintenance**: forks have diverged; the most active is `vis-timeline` (community fork). 1.5k stars.
- **Fit**: viable backup if react-calendar-timeline's reliance on moment becomes a maintenance issue.

## Decision

**Use `react-calendar-timeline`** (with the dayjs-based community fork if available, otherwise the original).

Reasoning:

1. **Correct gesture**: vertical-drag-across-rows is native, which matches the brewmaster's mental model (rows = tanks, dragging changes tank assignment).
2. **Bundle size acceptable**: ~70 KB is a small fraction of the React+TS baseline (~50 KB for React itself); we're not in a budget where this matters.
3. **No license cost**: MIT, no per-seat fees, aligns with Stefan's resource constraint.
4. **Lower implementation risk than frappe-gantt**: row-swap is a first-class feature, not an extension we'd have to maintain.

If react-calendar-timeline becomes a blocker (e.g. moment-related bugs, performance issues with the Pentecost peak load), the fallback is **vis-timeline**. frappe-gantt is rejected because its row binding doesn't fit the core gesture.

## What this decision is NOT

- **Not** a final UI design. Phase 1's Gantt is deliberately bare: rows for tanks, blocks for Süde, drag to reschedule, no validation overlays. Polish happens in Phase 2+.
- **Not** locked in for Phase 4. If the OR-Tools solver introduces visualization needs that exceed react-calendar-timeline (e.g. dependency arrows between Süde stages), revisit. The component is encapsulated in a single `<ScheduleBoard>` React component to keep the swap cost low.

## Resource budget impact

| Item | Estimate |
| --- | --- |
| Frontend bundle (Phase 1 total) | ~280 KB min+gzip (React + react-calendar-timeline + app code) |
| Static hosting cost | €0 — fits in Azure Static Web Apps free tier |
| License cost | €0 |

This stays well inside the "minimal resources" goal.
