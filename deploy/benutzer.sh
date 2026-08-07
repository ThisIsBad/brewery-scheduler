#!/usr/bin/env bash
# Konten verwalten, ohne deploy/.env von Hand zu editieren.
#
#   ./deploy/benutzer.sh stefan            Passwort wird abgefragt
#   ./deploy/benutzer.sh stefan 'geheim'   Passwort als Argument
#   ./deploy/benutzer.sh --entfernen alex
#   ./deploy/benutzer.sh --liste
#
# Das Passwort landet nie in der Datei — nur sein Hash. Wird es nicht als
# Argument übergeben, steht es auch nicht in der Shell-Historie.
set -euo pipefail

HIER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DATEI="$HIER/.env"
COMPOSE=(docker compose -f "$HIER/docker-compose.prod.yml" --env-file "$ENV_DATEI")

# Vier Plätze; der erste ist der ohne Nummer. Für mehr hier und in
# caddy-entrypoint.sh je eine Zeile ergänzen.
PLAETZE=("" "_2" "_3" "_4")

if [[ ! -f "$ENV_DATEI" ]]; then
	echo "Keine $ENV_DATEI — erst deploy/.env.example kopieren und ausfüllen." >&2
	exit 1
fi

wert_von() {
	sed -n "s/^$1=//p" "$ENV_DATEI" | head -1 | sed "s/^['\"]//; s/['\"]$//"
}

# Über ENVIRON statt -v, damit awk Zeichen im Hash nicht als Escapes liest.
setzen() {
	if grep -q "^$1=" "$ENV_DATEI"; then
		SCHLUESSEL="$1" WERT="$2" awk -F= \
			'$1 == ENVIRON["SCHLUESSEL"] { print ENVIRON["SCHLUESSEL"] "=" ENVIRON["WERT"]; next } { print }' \
			"$ENV_DATEI" > "$ENV_DATEI.neu"
		mv "$ENV_DATEI.neu" "$ENV_DATEI"
	else
		printf '%s=%s\n' "$1" "$2" >> "$ENV_DATEI"
	fi
}

liste() {
	echo "Konten:"
	for platz in "${PLAETZE[@]}"; do
		name="$(wert_von "BASIC_AUTH_USER$platz")"
		[[ -n "$name" ]] && echo "  - $name"
	done
	return 0
}

neu_starten() {
	cp "$ENV_DATEI" "$ENV_DATEI.bak"
	"${COMPOSE[@]}" up -d caddy
	echo
	liste
}

case "${1-}" in
--liste)
	liste
	exit 0
	;;
--entfernen)
	name="${2-}"
	[[ -n "$name" ]] || {
		echo "Wen entfernen? ./deploy/benutzer.sh --entfernen NAME" >&2
		exit 1
	}
	getroffen=""
	for platz in "${PLAETZE[@]}"; do
		if [[ "$(wert_von "BASIC_AUTH_USER$platz")" == "$name" ]]; then
			setzen "BASIC_AUTH_USER$platz" ""
			setzen "BASIC_AUTH_HASH$platz" ""
			getroffen="ja"
			break
		fi
	done
	[[ -n "$getroffen" ]] || {
		echo "Kein Konto namens '$name'." >&2
		exit 1
	}
	echo "'$name' entfernt."
	neu_starten
	exit 0
	;;
"" | --hilfe | -h)
	sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
	exit 0
	;;
esac

name="$1"
passwort="${2-}"
if [[ -z "$passwort" ]]; then
	read -rsp "Passwort für '$name': " passwort
	echo
	read -rsp "Zur Kontrolle wiederholen: " wiederholung
	echo
	[[ "$passwort" == "$wiederholung" ]] || {
		echo "Die Passwörter stimmen nicht überein." >&2
		exit 1
	}
fi
[[ -n "$passwort" ]] || {
	echo "Leeres Passwort geht nicht." >&2
	exit 1
}

# Auf dem Server gibt es kein caddy, dort erledigt es das Image.
if command -v caddy > /dev/null 2>&1; then
	hash="$(caddy hash-password --plaintext "$passwort")"
else
	hash="$(docker run --rm caddy:2 caddy hash-password --plaintext "$passwort")"
fi

ziel=""
gefunden=""
for platz in "${PLAETZE[@]}"; do
	if [[ "$(wert_von "BASIC_AUTH_USER$platz")" == "$name" ]]; then
		ziel="$platz"
		gefunden="vorhanden"
		break
	fi
done
if [[ -z "$gefunden" ]]; then
	for platz in "${PLAETZE[@]}"; do
		if [[ -z "$(wert_von "BASIC_AUTH_USER$platz")" ]]; then
			ziel="$platz"
			gefunden="frei"
			break
		fi
	done
fi
[[ -n "$gefunden" ]] || {
	echo "Alle ${#PLAETZE[@]} Plätze belegt — erst jemanden entfernen oder Plätze ergänzen." >&2
	exit 1
}

setzen "BASIC_AUTH_USER$ziel" "$name"
# Einfache Anführungszeichen: der Hash enthält $-Zeichen.
setzen "BASIC_AUTH_HASH$ziel" "'$hash'"

if [[ "$gefunden" == "vorhanden" ]]; then
	echo "Passwort von '$name' geändert."
else
	echo "'$name' angelegt."
fi
neu_starten
