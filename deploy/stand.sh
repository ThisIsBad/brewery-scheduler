#!/usr/bin/env bash
# Was läuft gerade wirklich auf diesem Server?
#
#   ./deploy/stand.sh            Bericht
#   ./deploy/stand.sh --pruefen  zusätzlich Exit 1, wenn der Stand nicht
#                                zum ausgecheckten Tag passt
#
# Gedacht gegen die Frage, die uns 2026-08-07 eine Stunde gekostet hat:
# ein Deploy kann durchlaufen, ohne dass sich etwas ändert.
set -euo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE=(docker compose -f "$HIER/docker-compose.prod.yml" --env-file "$HIER/.env")

# Ein frisch gebautes Image ist Minuten alt; alles darüber deutet darauf
# hin, dass der Bau übersprungen wurde.
MAX_ALTER_MINUTEN=${MAX_ALTER_MINUTEN:-90}

fehler=0
melden() { printf '  %-22s %s\n' "$1" "$2"; }

echo "Stand auf diesem Server"

tag="$(git -C "$HIER/.." describe --tags --always 2>/dev/null || echo "unbekannt")"
melden "Ausgecheckt:" "$tag"

image="$("${COMPOSE[@]}" images -q caddy 2>/dev/null | head -1)"
if [[ -z "$image" ]]; then
	melden "Bau der App:" "laeuft nicht"
	fehler=1
else
	gebaut="$(docker image inspect -f '{{.Created}}' "$image")"
	alter=$(((  $(date +%s) - $(date -d "$gebaut" +%s) ) / 60))
	melden "Bau der App:" "vor ${alter} min ($(date -d "$gebaut" '+%d.%m.%Y %H:%M'))"
	if ((alter > MAX_ALTER_MINUTEN)); then
		melden "" "⚠️  älter als ${MAX_ALTER_MINUTEN} min — wurde der Bau übersprungen?"
		fehler=1
	fi
fi

# Beweist, dass der Container die aktuelle Konfiguration trägt und nicht
# eine ältere Schicht aus dem Bau-Zwischenspeicher.
if "${COMPOSE[@]}" exec -T caddy grep -q "immutable" /etc/caddy/Caddyfile 2>/dev/null; then
	melden "Cache-Regeln:" "aktiv"
else
	melden "Cache-Regeln:" "⚠️  fehlen — Aktualisierungen erreichen die Handys nicht"
	fehler=1
fi

konten="$("${COMPOSE[@]}" exec -T caddy sh -c 'wc -l < /etc/caddy/benutzer.caddy' 2>/dev/null | tr -d '[:space:]' || echo "?")"
melden "Konten:" "$konten"

if [[ "${1-}" == "--pruefen" ]]; then
	exit "$fehler"
fi
