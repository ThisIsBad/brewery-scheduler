#!/usr/bin/env bash
# One-time dependency install after the Codespace is created.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "▸ Backend-Abhängigkeiten …"
python3 -m pip install --upgrade pip >/dev/null
python3 -m pip install -e "backend[dev]"

echo "▸ Frontend-Abhängigkeiten …"
cd frontend && npm ci --no-fund --no-audit
