#!/bin/sh
# Migrationen zuerst, dann die Stammdaten-Seeds (Tanks, Rezepte, Test-Sude —
# seed() überspringt sich selbst, sobald Tanks existieren), dann der Server.
set -e
alembic upgrade head
python -m brewery_scheduler.seed
exec uvicorn brewery_scheduler.main:app --host 0.0.0.0 --port 8000
