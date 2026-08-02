# Gantt component evaluation

**Status**: Superseded for Phase 2 — `react-calendar-timeline` shipped with the Phase-1 frontend (PR #5) as designed below, but the 2026-08 mobile-first decision (ROADMAP §2.8) triggered a touch re-evaluation. **Verdict: replace with a custom timeline on `@dnd-kit/core` in Phase 2 Track C** — see the addendum at the end of this document. The original evaluation below is kept for the desktop-era reasoning.

## Goal

Pick a Gantt/timeline component for the brewery scheduler frontend (Phase 1 onwards). The component is **the** core UX — drag-and-drop scheduling defines whether the brewmaster will adopt the tool. Constraints from Stefan:

> *"Mein Ziel ist, dass das Ganze mit möglichst wenig Ressourcen laufen kann."*

We optimize for low resource use first, then for fit.

## What "low resource" means here

| Dimension | Why it matters |
| --- | --- |
| **Frontend bundle size** | Loaded by every brewmaster on every visit; large bundles slow first paint and waste bandwidth. |
| **Runtime memory / DOM nodes** | The Gantt has up to 21 tank rows × ~100 visible Sude at peak (Pentecost). 2k–5k nodes is realistic. |
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
- **Fit**: best alignment with the "tanks-as-rows, drag-Sude-between-rows" gesture.

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

- **Not** a final UI design. Phase 1's Gantt is deliberately bare: rows for tanks, blocks for Sude, drag to reschedule, no validation overlays. Polish happens in Phase 2+.
- **Not** locked in for Phase 4. If the OR-Tools solver introduces visualization needs that exceed react-calendar-timeline (e.g. dependency arrows between Sude stages), revisit. The component is encapsulated in a single `<ScheduleBoard>` React component to keep the swap cost low.

## Resource budget impact

| Item | Estimate |
| --- | --- |
| Frontend bundle (Phase 1 total) | ~280 KB min+gzip (React + react-calendar-timeline + app code) |
| Static hosting cost | €0 — fits in Azure Static Web Apps free tier |
| License cost | €0 |

This stays well inside the "minimal resources" goal.

---

## Addendum (2026-08): touch-first re-evaluation

Trigger: ROADMAP §2.8 — primary usage is the phone, **including full planning**,
so the timeline must support one-handed touch drag/resize. Findings from the
research pass (sources linked in issue #10):

### Why react-calendar-timeline cannot become touch-first

- Interactions are delegated to **interact.js**, pinned at 1.10.27 — an
  effectively dormant engine (first release in ~2 years appeared 2026-08).
- Structural mobile gaps, unchanged in the 0.30 beta line: items must be
  tap-selected *before* they can be dragged or resized (upstream issue #694),
  touch drag fights page scroll (interact.js #595), no edge autoscroll while
  dragging (#783) — the exact gesture needed to move a block across 21 tank
  rows on a phone viewport.
- The project has been mid-rewrite (0.30.0-beta.x) since early 2025; stable
  is frozen at 0.28. Fine for viewing, not credible for touch-first editing.

### Alternatives assessed

| Option | Touch | License / cost | Verdict |
| --- | --- | --- | --- |
| **Custom on `@dnd-kit/core`** | Excellent: unified PointerSensor, long-press activation (preserves scroll), built-in autoscroll | MIT, ~10 kB | **Chosen** |
| Bryntum Scheduler | Best-in-class commercial | ~$2,040 (3 devs) + yearly | Fallback if custom build stalls |
| vis-timeline | OK (hammer.js), tap-then-drag | Apache-2.0 | Re-imports moment, no React wrapper — no |
| DHTMLX | Good | Timeline view is PRO-only | No |
| planby | Rows fit tanks | Drag/resize paywalled, single maintainer | No |
| Syncfusion | Good | Community license = revenue bet | No |
| SVAR Gantt | Good | MIT | Wrong shape (task tree, not resource rows) |

### Decision

Build the Phase-2 planning timeline as a **bespoke component on
`@dnd-kit/core` (stable 6.3.1)**: tank rows in a CSS grid over a time axis,
~200 ms long-press activation on touch, ≥44 px resize handles, dnd-kit
autoscroll for cross-row drags. Our domain is genuinely simple — flat
resource rows, no dependencies, no nesting — so ~500 bespoke lines are *less*
total complexity than configuring a general-purpose scheduler, and the swap
deletes `moment` and `interactjs` from the tree. This is consistent with the
"möglichst wenig Ressourcen" constraint that drove the original evaluation.

### Offline/PWA stack (same research pass)

- `vite-plugin-pwa` (`generateSW`): app-shell precache + `NetworkFirst`
  runtime caching of `GET /api/*` → the offline read cache.
- **No Workbox Background Sync** — iOS Safari has no Background Sync API at
  all, and Workbox treats a 409 reply as a *successful* replay and silently
  drops it, which would swallow exactly our double-booking conflicts.
- Mutation queue in the app layer instead: **TanStack Query v5** with
  `persistQueryClient` + storage persister; paused mutations replay via
  `resumePausedMutations()`; each mutation key registers
  `setMutationDefaults` at startup (persisted mutations lose their function
  on reload — known gotcha). A replayed 409 lands in the ordinary `onError`
  with our structured conflict body: the UI marks the booking "conflicted"
  and asks for a new slot, consistent with hard-block validation.
- Net dependency change: + `@dnd-kit/core`, `@tanstack/react-query` (+
  persist client), `vite-plugin-pwa`, `dayjs`; − `react-calendar-timeline`,
  `moment`, `interactjs`.
