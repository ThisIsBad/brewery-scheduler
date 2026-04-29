# brewery-scheduler

Constraint-aware scheduling and demand-planning tool for a craft brewery with a year-round beer garden and a 12-day Pentecost festival production cycle. Replaces the existing Excel-based workflow.

See [`ROADMAP.md`](./ROADMAP.md) for full domain context, data model, and phased plan.

## Status

Phase 1 (Walking Skeleton) — in progress. See open PRs.

This tranche covers the backend skeleton:
- FastAPI application with three Phase 1 endpoints (no validation — that's Phase 2)
- PostgreSQL schema via Alembic, including the `tank_occupancy` exclusion constraint
- Seed script with the real tank inventory from `ROADMAP.md` §2.2
- pytest smoke tests
- `docker-compose` for local Postgres + backend

The frontend (React + Gantt) lands in a follow-up PR.

## Repository layout

```
backend/   FastAPI + SQLAlchemy 2.x + Alembic
frontend/  Vite + React + TypeScript (added in PR 2)
infra/     docker-compose for local development
docs/      Design notes (Gantt component evaluation, etc.)
```

## Quick start (backend)

Requires Docker and Docker Compose.

```bash
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml up --build
```

Then in another terminal:

```bash
docker compose -f infra/docker-compose.yml exec backend alembic upgrade head
docker compose -f infra/docker-compose.yml exec backend python -m brewery_scheduler.seed
```

API available at <http://localhost:8000>, OpenAPI docs at <http://localhost:8000/docs>.

## Conventions

- All beer volumes in **hectoliters (hl)**; 1 hl = 100 l.
- Recipes are **versioned and immutable**: edits create a new row with `version + 1`.
- Tank double-booking is prevented at the database level via a GiST exclusion constraint (defense in depth beyond application-level validation, which arrives in Phase 2).
