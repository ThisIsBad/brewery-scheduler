#!/usr/bin/env bash
# Runs on every Codespace start/resume: migrate, seed, (re)start backend and
# frontend directly in this container. Idempotent; no terminal input needed
# (mobile browsers block pasting into the web terminal).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://brewery:brewery@${DB_HOST}:${DB_PORT}/brewery}"

echo "▸ Warte auf Postgres (${DB_HOST}) …"
for i in $(seq 1 60); do
  if python3 - <<EOF
import sys
import psycopg
try:
    psycopg.connect("host=${DB_HOST} port=${DB_PORT} user=brewery password=brewery dbname=brewery", connect_timeout=2).close()
except Exception:
    sys.exit(1)
EOF
  then
    break
  fi
  sleep 2
done

echo "▸ Migrationen + Seed …"
(cd backend && alembic upgrade head && python3 -m brewery_scheduler.seed)

echo "▸ Backend (Port 8000) …"
pkill -f "uvicorn brewery_scheduler.main" 2>/dev/null || true
sleep 1
nohup python3 -m uvicorn brewery_scheduler.main:app \
  --app-dir backend/src --host 0.0.0.0 --port 8000 \
  >/tmp/backend.log 2>&1 &
disown

echo "▸ Frontend (Port 5173) …"
pkill -f "vite" 2>/dev/null || true
sleep 1
cd "$ROOT/frontend"
nohup npm run dev >/tmp/frontend.log 2>&1 &
disown
cd "$ROOT"

# Fail loudly if either service does not come up — a silent half-start is
# exactly the bug this script replaces.
for i in $(seq 1 30); do
  ok_api=$(curl -sf http://localhost:8000/health >/dev/null && echo 1 || echo 0)
  ok_app=$(curl -sf http://localhost:5173 >/dev/null && echo 1 || echo 0)
  [ "$ok_api" = 1 ] && [ "$ok_app" = 1 ] && break
  sleep 2
done
if [ "$ok_api" != 1 ] || [ "$ok_app" != 1 ]; then
  echo "❌ Start unvollständig — Logs: /tmp/backend.log /tmp/frontend.log" >&2
  tail -20 /tmp/backend.log /tmp/frontend.log >&2 || true
  exit 1
fi

echo
echo "✅ Läuft — im Ports-Tab Port 5173 (Kellerblick) öffnen."
# Explicit exit so postStart terminates even if a stray child holds fds.
exit 0
