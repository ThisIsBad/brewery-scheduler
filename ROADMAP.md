# Brewery Scheduling & Planning App — Development Roadmap

## 1. Project Overview

A web-based scheduling and demand-planning tool for a craft brewery that operates a beer garden with a major seasonal festival production cycle (Pentecost). Replaces the current Excel-based planning workflow with a constraint-aware scheduler that optimizes batch (Sud) timing across fermentation, storage, and Ausschank tanks while respecting recipe rules, per-beer-style fermentation and storage durations, and the year-round demand for the beer garden alongside the Pentecost festival surge.

The app must integrate cleanly with the brewery's Microsoft 365 environment (Teams, Excel, SharePoint, Entra ID for SSO).

## 2. Domain Context

This section is the source of truth for the brewery's operational reality. All scheduling logic must respect these rules.

### 2.1 Terminology

| Term | Meaning |
| --- | --- |
| **Sud** (plural: **Sude**) | A single batch of brewed beer. Standard size: **15 hectoliters (hl)**. |
| **Hektoliter (hl)** | 100 liters. The standard volume unit in German breweries. |
| **Ausschank tank** | Final-stage tank from which beer is poured directly to customers (the brewery does not bottle). Lying-down tanks; beer must be free of active yeast before entering. |
| **Kellerbier** | The brewery's flagship year-round beer. |
| **Festbier** | Stronger seasonal beer brewed for the Pentecost festival. |
| **Open fermentation tank** | Special tank required only for wheat beer fermentation. |

### 2.2 Tank Inventory

All volumes in **hectoliters (hl)**. 1 hl = 100 l.

**Main cellar — fermentation tanks** (total capacity: **180 hl**)

- 5 × 30 hl (closed)
- 2 × 15 hl (closed)
- 1 × 15 hl (open — wheat beer only)

**Main cellar — storage tanks** (total: 150 hl)

- 5 × 30 hl

**Main cellar — Ausschank tanks** (total: 350 hl)

- 1 × 120 hl
- 1 × 100 hl
- 1 × 80 hl
- 1 × 50 hl

**Secondary cellar**

- 2 × 35 hl (Ausschank / final stage)
- 2 × 10 hl (storage)

### 2.3 Stage Progression

All beers follow this pipeline:

Brewhouse → Fermentation tank → Storage tank → Ausschank tank → Customer

**Wheat beer exception:** wheat beer requires an additional first step in the open fermentation tank (15 hl, 4 days) before transferring to a closed fermentation tank.

### 2.4 Hard Constraints

1. **Tank exclusivity:** A fermentation or storage tank holds at most one batch at a time. **Confirmed 2026-08 (issue #3):** the 30-hl case is real and typical — the same recipe is brewed twice within 48 hours and the two Sude are merged into one 30-hl tank, modeled as a *merged batch* (lead + partner, one tank occupant). **Ausschank tanks are different (confirmed 2026-08, issue #13):** they blend several batches at once, and a batch can be split across two Ausschank tanks (e.g. 6×30 hl → 100 + 80 hl). The `EXCLUDE` constraint therefore guards fermentation/storage only; Ausschank headroom (sum of allocations ≤ capacity) is enforced in the application.
2. **Yeast-free Ausschank:** Beer with active yeast cannot enter Ausschank (lying-down) tanks — residual yeast produces off-flavors ("hot sauces").
3. **Wheat-beer open fermentation prerequisite:** No wheat beer may enter a closed fermentation tank without first spending 4 days in the open fermentation tank.
4. **Stage ordering:** A Sud may only move forward in the pipeline (no Storage → Fermentation regression).

### 2.5 Annual Operational Cycle

| Period | Mode | Beers served |
| --- | --- | --- |
| April 1 → Sunday before Pentecost | **Regular beer garden** | Kellerbier, wheat beer, 2 special beers (4 always on tap) |
| Monday–Wednesday before Pentecost | **Changeover (3 days)** | Transition |
| Pentecost festival (**12 days**) | **Festival mode** | Festbier, wheat beer |
| 2 days post-festival | **Changeover** | Transition back |
| Post-festival → season end | **Regular beer garden** | Kellerbier, wheat beer, 2 special beers |

**Always-available constraint during regular operation:** Kellerbier, wheat beer, and both specials must be available continuously. Kellerbier specifically is served from the 50 hl Ausschank tank in regular operation.

### 2.6 Pentecost Production Targets

| Beer style | Sude | Volume |
| --- | --- | --- |
| Wheat beer | 3 | 45 hl |
| Kellerbier | 20 | 300 hl |
| Special beers | 6 | 90 hl |
| Festbier | 32 | 480 hl |
| **Total** | **61** | **915 hl** |

With only 180 hl of fermentation capacity (12 Sude concurrent maximum), this requires roughly 5–6 sequential fermentation cycles in the lead-up to Pentecost while simultaneously maintaining regular beer garden supply.

### 2.7 Per-Beer-Style Durations (to be filled in with brewmaster)

These values live in the recipe table and drive the solver. **Decision (2026-08, issue #2):** the placeholders below are confirmed as working values until the brewmaster session delivers real numbers — they are editable per recipe at any time, so nothing blocks on them. Whether durations vary by season is still open.

| Beer style | Open ferm. (days) | Closed ferm. (days) | Storage (days) | Max storage (days) |
| --- | --- | --- | --- | --- |
| Kellerbier | — | TBD | TBD | TBD |
| Wheat beer | 4 | TBD | TBD | TBD |
| Festbier | — | TBD | TBD | TBD |
| Specials | — | TBD | TBD | TBD |

### 2.8 Usage Context (confirmed 2026-08)

Primary usage is **mobile — the phone in the cellar is the main device**, for
all four core actions:

- checking tank status during cellar rounds
- booking transfers (Umdrücken) at the moment they happen
- creating new Sude
- **and full planning work** (moving Sude across weeks, Pentecost cycles)

Cellar connectivity is **spotty** (vaulted cellar, radio dead spots). Two
consequences, both architectural:

1. The frontend ships as a **PWA with an offline read cache and a queue for
   offline mutations** (create/transfer/reschedule are captured offline and
   replayed on reconnect; server-side 409 conflicts from the replay must
   surface clearly, not vanish).
2. Every user-facing feature is designed **mobile-first**; the desktop view
   is the derivative, not the other way around. Two parallel surfaces:
   - **Kellerblick** — card list per tank (contents, day N of M, next due
     action) with validated tap-flows for transfers; the everyday surface.
   - **Planning timeline** — the Gantt, made genuinely touch-capable
     (targets, zoom, tap-to-select-then-move); the planning surface.

This supersedes the older reading of §6.5 ("responsive web is sufficient"),
which had been interpreted desktop-first. No native app — the PWA is the
delivery model.

## 3. Tech Stack

| Layer | Choice | Rationale |
| --- | --- | --- |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.x | Mature ecosystem; native fit for OR-Tools; auto-generated OpenAPI docs |
| Solver | Google OR-Tools (CP-SAT) | Industry standard for resource-constrained scheduling; excellent Python bindings |
| Database | PostgreSQL 16 | Strong relational integrity; native tstzrange for tank occupancy windows |
| Frontend | React 18 + TypeScript, Vite | Standard, well-supported |
| Timeline component | react-calendar-timeline (Phase 1) → **custom timeline on `@dnd-kit/core` in Phase 2 Track C** | Touch re-evaluation (docs/gantt-evaluation.md addendum): rct's interaction engine can't be made touch-first; our flat tank-row domain makes a ~500-line bespoke component the lowest-complexity option, and the swap removes moment + interactjs |
| PWA / offline | vite-plugin-pwa (`generateSW`) for the offline read cache; **TanStack Query v5** persisted-mutation queue for offline writes — explicitly *no* Workbox Background Sync | iOS has no Background Sync API, and Workbox drops 409 replies silently — our double-booking conflicts must instead land in normal `onError` UI (see gantt-evaluation.md addendum) |
| Auth | Microsoft Entra ID via MSAL | Native M365 integration; SSO from Teams |
| Hosting | Azure App Service (Linux, B1 tier) for API; Azure Static Web Apps for frontend; Azure PostgreSQL Flexible Server (burstable) | Aligns with M365 stack; estimated infra cost ~€30–40/month |
| Excel I/O | OpenPyXL | Two-way sync with brewmaster's existing Excel workflow |
| Async job queue | Celery + Redis | Needed from Phase 4 for full re-optimization runs |
| Forecasting | statsmodels (classical) or Prophet (Meta) | Phase 6+ |
| Observability | OpenTelemetry → Azure Monitor | Standard, low-effort to add |
| Containerization | Docker + docker-compose for local dev | Mirror production environment |

## 4. Data Model (Initial Sketch)

Core tables. The schema is the highest-leverage thing to get right because it's the hardest to change later. **Spend extra time here in Phase 1.**

**recipes**

- `id` (uuid, pk)
- `beer_style` (enum: kellerbier, wheat, festbier, special)
- `version` (int, monotonically increasing per beer_style)
- `name` (text)
- `ingredients` (jsonb)
- `mash_schedule` (jsonb)
- `hop_additions` (jsonb)
- `fermentation_temp_c` (numeric)
- `fermentation_duration_days` (numeric)
- `open_fermentation_required` (bool)
- `open_fermentation_duration_days` (numeric, nullable)
- `storage_duration_days` (numeric)
- `max_storage_duration_days` (numeric)
- `created_at` (timestamptz)
- `created_by` (text)
- `notes` (text)
- UNIQUE (beer_style, version)

**tanks**

- `id` (uuid, pk)
- `name` (text, e.g. "F1", "S3", "A-50")
- `cellar` (enum: main, secondary)
- `stage` (enum: fermentation_open, fermentation_closed, storage, ausschank)
- `capacity_hl` (numeric)
- `active` (bool)

**sude**

- `id` (uuid, pk)
- `recipe_id` (uuid, fk → recipes.id)
- `recipe_overrides` (jsonb, nullable)
- `brew_date` (date)
- `status` (enum: planned, brewing, fermenting, storing, in_ausschank, served, discarded)
- `notes` (text)
- `brewmaster` (text)

**tank_occupancy**

- `id` (uuid, pk)
- `sud_id` (uuid, fk → sude.id)
- `tank_id` (uuid, fk → tanks.id)
- `stage` (enum: fermentation_open, fermentation_closed, storage, ausschank)
- `start_at` (timestamptz)
- `end_at` (timestamptz, nullable while occupied)
- `EXCLUDE USING gist (tank_id WITH =, tstzrange(start_at, end_at) WITH &&)`
- The exclusion constraint enforces: no two occupancies of the same tank with overlapping time ranges

**sales** (Phase 6+)

- `id` (uuid, pk)
- `sale_date` (date)
- `beer_style` (text)
- `hectoliters` (numeric)
- `source` (enum: pos_import, manual, estimated)

**demand_forecasts** (Phase 6+)

- `id` (uuid, pk)
- `generated_at` (timestamptz)
- `forecast_method` (text)
- `week_starting` (date)
- `beer_style` (text)
- `forecasted_hl` (numeric)
- `human_override_hl` (numeric, nullable)
- `approved` (bool, default false)
- `approved_by` (text, nullable)

**Key design notes:**

- Recipes are **versioned, immutable**. Updating a recipe creates a new row with version + 1. Existing Sude keep their original recipe link.
- `recipe_overrides` on `sude` allows per-Sud brewmaster adjustments without polluting the recipe table.
- The PostgreSQL `EXCLUDE USING gist` constraint on `tank_occupancy` enforces no double-booking of tanks at the database level — defense in depth beyond application logic.

## 5. Development Phases

The guiding principle: **walking skeleton**. Build a thin vertical slice (frontend → backend → database) first, then add intelligence layer by layer. **Every phase ends with a deployable, brewmaster-testable system.**

### Phase 1 — Walking Skeleton (1–2 weeks) — ✅ fertig (2026-08)

**Goal:** prove the end-to-end round trip works.

- Set up monorepo: `/backend` (FastAPI), `/frontend` (Vite + React), `/infra` (Bicep or Terraform for Azure)
- Postgres schema migrations via Alembic — create the tables from §4
- Seed data: real tank inventory from §2.2, placeholder recipes, a handful of test Sude
- Three FastAPI endpoints:
  - `GET /api/tanks` — list tanks with current occupancy
  - `GET /api/sude` — list Sude with their tank assignments and time windows
  - `PUT /api/sude/{id}/schedule` — update a Sud's tank assignment and time window (no application-level validation)
- React frontend with Gantt view: tanks as rows, time as horizontal axis, Sude as draggable blocks
- **No application validation. No solver. No conflict highlighting.** The one exception, per §4: the database-level `EXCLUDE` constraint rejects overlapping occupancies of the same tank — an overlapping drop fails (currently as an unstructured error; Phase 2 turns this into a structured 409 with conflict details). Everything else — wrong stage, wrong capacity, impossible dates — saves without complaint.

**Definition of done:** brewmaster can open the app, see the tanks rendered, drag a Sud, and the change persists across page reload.

### Phase 2 — Validation Layer + Mobile Surfaces (3–4 weeks, re-scoped 2026-08) — ✅ Tracks A/B/C fertig (2026-08-04); offen: Offline-Mutations-Queue (issue #10). Feldentscheidung 2026-08-03: Prozessregeln warnen statt zu blockieren; nur physikalische Grenzen blocken hart.

**Goal:** encode all hard constraints from §2.4 as backend validation, and
deliver the two mobile-first surfaces from §2.8 on top of them.

**Track A — validation core (backend):**

- Validation blocks **hard** — no override mechanism (decided 2026-08)
- Backend rejects invalid actions with structured error responses
  (extending the 409/422 constraint contract shipped in PR #9):
  - Tank double-booking (done at DB level; application check adds detail)
  - Tank capacity vs. batch size
  - Wheat beer skipping open fermentation
  - Beer entering Ausschank with active yeast (fermentation not complete)
  - Stage regression
- **Merged-batch model** (issue #3): same recipe brewed twice within 48 h
  merges into one 30-hl tank — model explicitly, don't relax the EXCLUDE
  constraint
- `POST /api/sude/{id}/transfer` — the validated "move to next stage"
  action the tap-flows are built on
- Per-recipe duration calculations: dropping a Sud at brew date X derives
  expected fermentation/storage end dates
- DB-level uniqueness for `style_year_number` (deferred from PR #6)

**Track B — Kellerblick (mobile-first everyday surface):**

- Card list per tank: contents, Sud-Nr., day N of M, next due action
- Tap-flow transfers using Track A's endpoint: pick target tank from the
  valid candidates only, confirm, done
- PWA baseline: installable, offline read cache, offline mutation queue
  with visible replay/conflict status

**Track C — touch-capable planning timeline:**

- Outcome of the Gantt touch evaluation (docs/gantt-evaluation.md):
  either make react-calendar-timeline genuinely touch-capable or swap it
- Conflict visualization: invalid placements flagged with the reason
- Larger touch targets, pinch zoom, tap-to-select-then-move

**This phase is where edge cases get discovered.** Plan a working session
with the brewmaster — in the cellar, on the phone, over real radio dead
spots.

**Definition of done:** brewmaster can run a full cellar day from the
phone — check status, book a transfer, create a Sud, adjust the plan —
without being able to create an invalid schedule, even with intermittent
connectivity.

### Phase 3 — Recipe Management (1 week) — ✅ fertig (2026-08-04)

**Goal:** brewmaster can manage recipes with full version history.

- CRUD endpoints for recipes (create new version, view history, view diff between versions)
- Frontend recipe editor with template + override workflow
- "Create new version" workflow — never edit in place
- Per-Sud override UI: brewmaster can deviate from recipe defaults for a single batch and the override is recorded
- Recipe history view: see all versions of Kellerbier over time, when they changed, who changed them

**Decision (2026-08, issue #4): keep.** Already-scheduled Sude retain their original recipe version; new Sude use the latest version; one-off deviations go through `recipe_overrides`. No re-link UI.

**Definition of done:** brewmaster can update a recipe, see the history, and trust that past Sude retain their original recipe data.

### Phase 4 — Solver Integration (2–3 weeks)

**Goal:** the system can generate optimal schedules, not just validate manual ones.

- OR-Tools CP-SAT model encoding all constraints from §2.4 plus:
  - Tank capacity matching (Sud size ≤ tank capacity)
  - Per-beer-style duration windows
  - Demand calendar (which beer needs to be in which Ausschank tank during which date range)
- Two solver modes:
  - **Sync (small reschedule):** drag a Sud → solver re-validates downstream impacts in <1s → returns suggested adjustments
  - **Async (full replan):** "Plan the next 12 weeks" → Celery job → solver runs for up to 60s → result delivered via WebSocket or polling
- Frontend "Suggest schedule" button + diff view showing solver output vs current plan
- A/B comparison: brewmaster can keep their manual plan or accept the solver's

**Definition of done:** brewmaster runs "plan Pentecost" and gets a feasible schedule that respects all constraints. Compare to last year's manual plan.

### Phase 5 — M365 Integration (1–2 weeks)

**Goal:** the app lives where the brewmaster already works.

- Teams app manifest (use Microsoft Teams Toolkit for VS Code)
- Entra ID app registration; SSO so users in Teams don't see a separate login
- Excel two-way sync via OpenPyXL:
  - Export current schedule to .xlsx
  - Re-import edited .xlsx with reconciliation
- SharePoint export for weekly schedule PDFs (via Microsoft Graph API)
- Pin app as a tab in the brewery's Teams channel

**Definition of done:** brewmaster opens Teams, clicks the brewery tab, and is logged in automatically.

### Phase 6 — Sales History & Demand Forecasting (2 weeks)

**Goal:** turn the scheduler into a demand-driven planner.

- Sales import:
  - One-time bulk import of historical sales from POS Excel exports (or whatever source the brewery has)
  - Ongoing weekly Excel upload, or POS API integration if available
- Forecasting:
  - Start simple: "same week last year, adjusted for trend percentage"
  - Then layer in seasonal decomposition (statsmodels) or Prophet
  - Per-beer-style, per-week granularity
- UI: chart view of historical sales, forecast curve overlay, year-over-year comparison

**Definition of done:** brewmaster can see "here's what we sold last Pentecost, and here's the model's forecast for this year" with clear visualizations.

### Phase 7 — Forecast-Driven Scheduling (1–2 weeks)

**Goal:** close the loop — forecast becomes solver input, with human-in-the-loop approval.

- Forecast review/approval workflow:
  - Solver produces a forecast → brewmaster reviews → can override per-week/per-beer values → marks as approved
  - Override reasons captured (e.g. "wedding booking weekend 3", "competitor closed", "warm weather expected")
- Approved forecast feeds into solver as the demand curve
- Side-by-side display: model prediction vs human override, with delta clearly visible

**Definition of done:** end-to-end pipeline from historical sales → forecast → human-adjusted forecast → solver-generated schedule.

## 6. Cross-Cutting Considerations

### 6.1 Testing

- Backend: pytest for unit tests, plus a dedicated test suite for the solver (regression suite of "known good" schedules, plus property-based tests via Hypothesis for constraint satisfaction)
- Frontend: Vitest + React Testing Library for components; Playwright for end-to-end Gantt drag-and-drop scenarios
- The solver test suite is the most important test suite in the codebase — it should grow whenever a new edge case is discovered

### 6.2 Logging & Observability

Structured JSON logs from day one (consistent with Stefan's preference for structured logging in Noesis). Log every solver run with input/output/duration so future calibration is possible.

### 6.3 Authentication & Authorization

- All endpoints require authenticated user (Entra ID JWT)
- Two roles initially: brewmaster (full read/write) and viewer (read-only)
- Audit log of all mutations (who changed what when)

### 6.4 Local Development

- `docker-compose up` brings up Postgres, Redis, the backend, and the frontend
- Seed script populates realistic test data (the actual tank inventory, sample recipes, a few Sude)
- `.env.example` documents all required environment variables

### 6.5 What NOT to Build

Explicitly out of scope to prevent scope creep:

- Native mobile app (App Store / Play Store) — the mobile-first **PWA** from §2.8 is the delivery model
- Multi-brewery support (single tenant)
- Inventory management (ingredients, hops, malt) — separate concern
- Sales/POS integration as a service (Excel import is enough)
- Microservices, Kubernetes, or any distributed-systems complexity
- Real-time IoT integration with tank sensors (interesting future, but not v1)

## 7. Recommended First Actions for Claude Code

1. Initialize the monorepo with the structure described in Phase 1
2. Set up the Postgres schema and Alembic migrations using the data model in §4
3. Implement seed data using the actual tank inventory from §2.2
4. Build the three Phase 1 endpoints
5. Choose and integrate the Gantt component (this decision blocks frontend work — evaluate frappe-gantt first since it's free)
6. Get the basic drag-and-drop working with no validation
7. **Stop and demo to Stefan and the brewmaster before starting Phase 2.**

---

*Last updated: 2026-08-04. This roadmap is a living document — update as priorities shift and edge cases emerge. Offene Fragen und nächste Schritte: docs/PLANUNG.md.*
