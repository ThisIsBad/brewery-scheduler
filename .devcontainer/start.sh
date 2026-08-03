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

# The node feature installs via nvm; a non-interactive postStart shell can
# miss its PATH entry even though setup.sh saw it.
if ! command -v npm >/dev/null 2>&1 && [ -s /usr/local/share/nvm/nvm.sh ]; then
  export NVM_DIR=/usr/local/share/nvm
  set +eu
  . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
  set -eu
fi

# Self-heal a torn postCreate (interrupted pip/npm install): reinstall what is
# missing instead of failing later with a dead port. Non-fatal — the health
# gate below reports whatever still doesn't come up.
python3 -c "import uvicorn, alembic, psycopg" 2>/dev/null \
  || python3 -m pip install -e "backend[dev]" || true
[ -x frontend/node_modules/.bin/vite ] \
  || (cd frontend && npm ci --no-fund --no-audit) || true

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

# Fail loudly if either service does not come up — and leave the evidence in
# a file the Explorer can open, because mobile users cannot copy from the
# terminal and never see the creation log.
for i in $(seq 1 30); do
  ok_api=$(curl -sf http://localhost:8000/health >/dev/null && echo 1 || echo 0)
  ok_app=$(curl -sf http://localhost:5173 >/dev/null && echo 1 || echo 0)
  [ "$ok_api" = 1 ] && [ "$ok_app" = 1 ] && break
  sleep 2
done
if [ "$ok_api" != 1 ] || [ "$ok_app" != 1 ]; then
  {
    echo "Start unvollständig ($(date '+%Y-%m-%d %H:%M:%S'))"
    echo "Backend  (Port 8000): $([ "$ok_api" = 1 ] && echo OK || echo FEHLT)"
    echo "Frontend (Port 5173): $([ "$ok_app" = 1 ] && echo OK || echo FEHLT)"
    echo "node: $(command -v node >/dev/null && node --version || echo FEHLT)   npm: $(command -v npm >/dev/null && npm --version || echo FEHLT)"
    free -m 2>/dev/null | head -2 || true
    echo
    echo "── /tmp/backend.log (Ende) ──"
    tail -40 /tmp/backend.log 2>/dev/null || true
    echo
    echo "── /tmp/frontend.log (Ende) ──"
    tail -40 /tmp/frontend.log 2>/dev/null || true
  } | tee STARTUP-FEHLER.txt >&2
  echo "❌ Start unvollständig — STARTUP-FEHLER.txt im Datei-Explorer antippen, Screenshot genügt." >&2
  exit 1
fi

rm -f STARTUP-FEHLER.txt
echo
echo "✅ Läuft — im Ports-Tab Port 5173 (Kellerblick) öffnen."
# Explicit exit so postStart terminates even if a stray child holds fds.
exit 0
