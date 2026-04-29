# brewery-scheduler

Constraint-aware scheduling and demand-planning tool for a craft brewery with a year-round beer garden and a 12-day Pentecost festival production cycle. Replaces the existing Excel-based workflow.

See [`ROADMAP.md`](./ROADMAP.md) for full domain context, data model, and phased plan.

## Status

Phase 1 (Walking Skeleton). Backend tranche merged; frontend tranche in PR.

## Repository layout

```
backend/   FastAPI + SQLAlchemy 2.x + Alembic
frontend/  Vite + React + TypeScript + react-calendar-timeline
infra/     docker-compose for local development
docs/      Design notes (Gantt component evaluation, etc.)
```

## Quick start

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
