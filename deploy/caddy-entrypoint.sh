#!/bin/sh
# Baut die Kontenliste für Basic-Auth aus den BASIC_AUTH_*-Variablen.
# Feste Plätze in der Caddyfile hätten für jeden unbenutzten Platz einen
# gültigen Hash gebraucht; so trägt deploy/.env einfach so viele Paare,
# wie es Personen gibt.
set -e

LISTE=/etc/caddy/benutzer.caddy
: > "$LISTE"

eintragen() {
	if [ -n "$1" ] && [ -n "$2" ]; then
		printf '\t%s %s\n' "$1" "$2" >> "$LISTE"
	fi
}

eintragen "$BASIC_AUTH_USER" "$BASIC_AUTH_HASH"
eintragen "$BASIC_AUTH_USER_2" "$BASIC_AUTH_HASH_2"
eintragen "$BASIC_AUTH_USER_3" "$BASIC_AUTH_HASH_3"
eintragen "$BASIC_AUTH_USER_4" "$BASIC_AUTH_HASH_4"

# Lieber gar nicht starten als ungeschützt ausliefern.
if [ ! -s "$LISTE" ]; then
	echo "Kein Basic-Auth-Konto konfiguriert — BASIC_AUTH_USER und BASIC_AUTH_HASH in deploy/.env setzen." >&2
	exit 1
fi

echo "Basic-Auth-Konten: $(wc -l < "$LISTE")"
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
