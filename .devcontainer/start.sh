#!/usr/bin/env bash
# Codespace autostart: bring up the full stack, migrate, seed — no terminal
# input needed (mobile browsers often block pasting into the web terminal).
# Idempotent: safe on every Codespace resume.
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f infra/.env ] || cp infra/.env.example infra/.env

docker compose -f infra/docker-compose.yml up -d --build

# The db service gates on its healthcheck via depends_on, but give the
# backend a moment to boot before running migrations, and retry once —
# first boots on cold Codespaces can be slow.
for attempt in 1 2 3; do
  if docker compose -f infra/docker-compose.yml exec -T backend alembic upgrade head; then
    break
  fi
  echo "Migration attempt ${attempt} failed — retrying in 5s …"
  sleep 5
done

docker compose -f infra/docker-compose.yml exec -T backend python -m brewery_scheduler.seed

echo
echo "✅ Stack läuft — App im Ports-Tab: Port 5173 (Kellerblick) öffnen."
