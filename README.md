# brewery-scheduler

Constraint-aware scheduling and demand-planning tool for a craft brewery with a year-round beer garden and a 12-day Pentecost festival production cycle. Replaces the existing Excel-based workflow.

See [`ROADMAP.md`](./ROADMAP.md) for full domain context, data model, and phased plan.

## Status

Phase 1 (Walking Skeleton) complete: backend, Gantt frontend, and Sud numbering are merged. The Create-Sud workflow is in review. Next up: Phase 2 (validation layer) — see the open issues for the decisions feeding into it.

## Repository layout

```
backend/   FastAPI + SQLAlchemy 2.x + Alembic
frontend/  Vite + React + TypeScript + react-calendar-timeline
infra/     docker-compose for local development
docs/      Design notes (Gantt component evaluation, etc.)
```

## Quick start — GitHub Codespaces (zero typing)

Open the repo → `<> Code` → **Codespaces** → create/open a Codespace on `main`.
The devcontainer starts Postgres, backend and frontend, applies migrations and
seeds automatically (`.devcontainer/start.sh`). When the ports notification
appears, open **port 5173** in the browser — done. To restart the stack
manually, a single word suffices in the terminal: `./up`

## Quick start — local Docker

Requires Docker and Docker Compose.

```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml up --build
```

Then in another terminal, apply migrations and seed:

```bash
docker compose -f infra/docker-compose.yml exec backend alembic upgrade head
docker compose -f infra/docker-compose.yml exec backend python -m brewery_scheduler.seed
```

- Backend API: <http://localhost:8000>, OpenAPI docs at <http://localhost:8000/docs>
- Frontend: <http://localhost:5173>

## Frontend dev (without Docker)

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` and `/health` to `VITE_BACKEND_URL` (default `http://localhost:8000`), so the backend should be running locally too.

## Conventions

- All beer volumes in **hectoliters (hl)**; 1 hl = 100 l.
- Recipes are **versioned and immutable**: edits create a new row with `version + 1`.
- Tank double-booking is prevented at the database level via a GiST exclusion constraint (defense in depth beyond application-level validation, which arrives in Phase 2).
- **Sud numbering**: every Sud has two numbers — a `global_number` (sequential across all years and styles, internal-only) and a `style_year_number` (sequential per beer style per year, shown to the brewmaster as `Kellerbier Nr. 17/2026`).

## Go-live: set the starting global Sud number

If the brewery already has a Sud counter from its previous workflow, set the offset before the first real brew is logged:

```bash
docker compose -f infra/docker-compose.yml exec backend \
  python -m brewery_scheduler.set_global_seq 5472
```

The next inserted Sud gets `global_number = 5472`. The script refuses to set a value below the highest existing `global_number` to avoid duplicate-key errors. Run only once at go-live; the sequence advances on its own afterwards.
