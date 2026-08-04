#!/usr/bin/env bash
# One-time dependency install after the Codespace is created. Deliberately
# non-fatal: if a step fails (transient npm/network error), postStart still
# runs — start.sh self-heals missing dependencies and reports loudly.
set -uo pipefail
cd "$(dirname "$0")/.."

echo "▸ Backend-Abhängigkeiten …"
python3 -m pip install --upgrade pip >/dev/null || true
python3 -m pip install -e "backend[dev]" \
  || echo "⚠ pip install fehlgeschlagen — start.sh repariert das beim Start."

echo "▸ Frontend-Abhängigkeiten …"
(cd frontend && npm ci --no-fund --no-audit) \
  || echo "⚠ npm ci fehlgeschlagen — start.sh repariert das beim Start."

# Seed the dependency fingerprint so start.sh skips the reinstall check
# on a fresh Codespace (it re-runs only when the lockfile moves).
cat backend/pyproject.toml frontend/package-lock.json 2>/dev/null \
  | md5sum | cut -d' ' -f1 > .deps-fingerprint || true

exit 0
