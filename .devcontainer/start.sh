#!/usr/bin/env bash
# Runs on every Codespace start/resume: migrate, seed, (re)start backend and
# frontend directly in this container. Idempotent; no terminal input needed
# (mobile browsers block pasting into the web terminal).
#
# Observability contract for mobile debugging:
#   STARTUP-STATUS.txt  — always written; shows the current phase / outcome.
#   STARTUP-FEHLER.txt  — written on ANY failure (not just the health gate),
#                         removed again by a successful start.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_WAIT_TRIES="${DB_WAIT_TRIES:-60}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://brewery:brewery@${DB_HOST}:${DB_PORT}/brewery}"

# Full transcript of this run, referenced by the failure report.
echo "── start.sh $(date '+%Y-%m-%d %H:%M:%S') ──" >> /tmp/start.log
exec > >(tee -a /tmp/start.log) 2>&1

PHASE="Init"
ok_api="?"
ok_app="?"

verdict() { case "$1" in 1) echo "OK" ;; 0) echo "FEHLT" ;; *) echo "(nicht geprüft)" ;; esac; }

status_file() {
  {
    echo "$1"
    echo "Skript-Stand: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo '?')"
  } > "$ROOT/STARTUP-STATUS.txt"
}

phase() {
  PHASE="$1"
  status_file "⏳ ${PHASE} … (seit $(date '+%H:%M:%S'))"
  echo "▸ ${PHASE} …"
}

# Any nonzero exit — DB timeout, migration crash, dead service — leaves a
# report the Explorer can open; mobile users never see the creation log.
on_exit() {
  status=$?
  [ "$status" -eq 0 ] && return 0
  {
    echo "❌ Start fehlgeschlagen in Phase: ${PHASE} ($(date '+%Y-%m-%d %H:%M:%S'))"
    echo "Backend  (Port 8000): $(verdict "$ok_api")"
    echo "Frontend (Port 5173): $(verdict "$ok_app")"
    echo "node: $(command -v node >/dev/null && node --version || echo FEHLT)   npm: $(command -v npm >/dev/null && npm --version || echo FEHLT)"
    free -m 2>/dev/null | head -2 || true
    echo
    echo "── Skript-Ausgabe (Ende) ──"
    tail -25 /tmp/start.log 2>/dev/null || true
    echo
    echo "── /tmp/backend.log (Ende) ──"
    tail -25 /tmp/backend.log 2>/dev/null || true
    echo
    echo "── /tmp/frontend.log (Ende) ──"
    tail -25 /tmp/frontend.log 2>/dev/null || true
  } > "$ROOT/STARTUP-FEHLER.txt"
  status_file "❌ Fehlgeschlagen in Phase: ${PHASE} — Details in STARTUP-FEHLER.txt"
  echo "❌ Start unvollständig — STARTUP-FEHLER.txt im Datei-Explorer antippen, Screenshot genügt." >&2
}
trap on_exit EXIT

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
phase "Abhängigkeiten prüfen"
python3 -c "import uvicorn, alembic, psycopg" 2>/dev/null \
  || python3 -m pip install -e "backend[dev]" || true
[ -x frontend/node_modules/.bin/vite ] \
  || (cd frontend && npm ci --no-fund --no-audit) || true

phase "Warte auf Postgres (${DB_HOST})"
db_up=0
for i in $(seq 1 "$DB_WAIT_TRIES"); do
  if python3 - <<EOF
import sys
import psycopg
try:
    psycopg.connect("host=${DB_HOST} port=${DB_PORT} user=brewery password=brewery dbname=brewery", connect_timeout=2).close()
except Exception:
    sys.exit(1)
EOF
  then
    db_up=1
    break
  fi
  sleep 2
done
if [ "$db_up" != 1 ]; then
  echo "Postgres unter ${DB_HOST}:${DB_PORT} nicht erreichbar." >&2
  exit 1
fi

phase "Migrationen + Seed"
(cd backend && alembic upgrade head && python3 -m brewery_scheduler.seed)

# Services run under tiny watchdog loops: if uvicorn or vite dies later
# (OOM, crash), it restarts within 5 s instead of leaving a dead port. The
# ": keller-watchdog-*" no-op puts a kill marker into the command line.
phase "Backend starten (Port 8000)"
pkill -f "keller-watchdog-backend" 2>/dev/null || true
pkill -f "uvicorn brewery_scheduler.main" 2>/dev/null || true
sleep 1
nohup bash -c ": keller-watchdog-backend; cd \"$ROOT\"; while true; do \
  python3 -m uvicorn brewery_scheduler.main:app --app-dir backend/src --host 0.0.0.0 --port 8000 >>/tmp/backend.log 2>&1; \
  echo \"[watchdog] Backend beendet (\$(date '+%H:%M:%S')) — Neustart in 5s\" >>/tmp/backend.log; sleep 5; done" \
  >/dev/null 2>&1 &
disown

phase "Frontend starten (Port 5173)"
pkill -f "keller-watchdog-frontend" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
sleep 1
nohup bash -c ": keller-watchdog-frontend; cd \"$ROOT/frontend\"; while true; do \
  npm run dev >>/tmp/frontend.log 2>&1; \
  echo \"[watchdog] Frontend beendet (\$(date '+%H:%M:%S')) — Neustart in 5s\" >>/tmp/frontend.log; sleep 5; done" \
  >/dev/null 2>&1 &
disown

phase "Health-Gate"
for i in $(seq 1 30); do
  ok_api=$(curl -sf http://localhost:8000/health >/dev/null && echo 1 || echo 0)
  ok_app=$(curl -sf http://localhost:5173 >/dev/null && echo 1 || echo 0)
  [ "$ok_api" = 1 ] && [ "$ok_app" = 1 ] && break
  sleep 2
done
if [ "$ok_api" != 1 ] || [ "$ok_app" != 1 ]; then
  exit 1
fi

rm -f "$ROOT/STARTUP-FEHLER.txt"
status_file "✅ Läuft seit $(date '+%Y-%m-%d %H:%M:%S') — Backend OK, Frontend OK"
echo
echo "✅ Läuft — im Ports-Tab Port 5173 (Kellerblick) öffnen."
# Explicit exit so postStart terminates even if a stray child holds fds.
exit 0
