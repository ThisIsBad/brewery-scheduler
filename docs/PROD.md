# Produktivbetrieb (MVP-Test mit Vincenz)

Stand 2026-08-05. Ein Server (Hetzner-Tendenz aus der Planungsrunde; jede
kleine Linux-VM mit Docker tut es), ein Stack, Basic-Auth davor. Die
Testdaten (Tanks, deine 10 Rezepte, Beispiel-Sude) werden beim ersten
Start automatisch eingespielt.

## Dev / Prod in einem Satz

**`main` ist Dev** (Codespace wie bisher, jede Änderung landet dort
automatisch). **Ein Versions-Tag `v*` ist ein Prod-Release** — Prod ändert
sich nur, wenn bewusst getaggt wird, egal wie viel auf `main` passiert.

## Server einmalig einrichten (~15 Minuten)

Auf einer frischen VM (Debian/Ubuntu, z. B. Hetzner CX22, ~5 €/Monat):

```bash
# 1) Docker
curl -fsSL https://get.docker.com | sh

# 2) Code
sudo mkdir -p /opt/brewery-scheduler && sudo chown "$USER" /opt/brewery-scheduler
git clone https://github.com/ThisIsBad/brewery-scheduler.git /opt/brewery-scheduler
cd /opt/brewery-scheduler
git checkout v0.1.0          # das MVP-Release, nicht main

# 3) Konfiguration
cp deploy/.env.example deploy/.env
docker run --rm caddy:2 caddy hash-password --plaintext 'GEHEIMES-PASSWORT'
#   -> Hash in deploy/.env bei BASIC_AUTH_HASH eintragen,
#      POSTGRES_PASSWORD setzen, SITE_ADDRESS: Domain oder ":80"

# 4) Start
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d --build
```

Danach: `http(s)://SERVER` öffnen, mit `vincenz` + Passwort anmelden, am
Handy „Zum Startbildschirm hinzufügen" (PWA).

- **Mit Domain** (DNS-A-Record auf die Server-IP): automatisches HTTPS
  über Let's Encrypt, nichts weiter zu tun.
- **Ohne Domain** (`SITE_ADDRESS=:80`): läuft über die IP ohne TLS —
  fürs interne Testen okay, vor echten Daten bitte Domain nachziehen.

## Automatisches Deploy bei Tags (optional, empfohlen)

Einmalig im GitHub-Repo:

1. **Secrets** (Settings → Secrets → Actions): `PROD_HOST` (IP/Domain),
   `PROD_USER` (SSH-Benutzer), `PROD_SSH_KEY` (privater Deploy-Key; das
   Gegenstück in `~/.ssh/authorized_keys` des Servers).
2. **Variable** (Settings → Variables → Actions):
   `PROD_DEPLOY_ENABLED = true`.

Ab dann gilt: `git tag v0.1.1 && git push origin v0.1.1` → der Server
zieht das Tag und baut neu (`.github/workflows/deploy.yml`). Ohne die
Variable bleibt Tagging folgenlos — der Workflow startet gar nicht erst.

## Backups

Der `backup`-Container legt täglich um ca. 03:00 einen Dump nach
`deploy/backups/brewery-JJJJ-MM-TT.dump` (14 Tage Aufbewahrung).

Wiederherstellen:

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env exec -T db \
  pg_restore -U brewery -d brewery --clean --if-exists /backups/brewery-JJJJ-MM-TT.dump
```

Die Dumps liegen nur auf dem Server — sobald der Hetzner-Umzug final ist,
zusätzlich per Cron auf eine Storage Box spiegeln (Dezember-Thema).

## Testdaten zurücksetzen

Für die Testphase jederzeit erlaubt (löscht ALLES und seedet neu):

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env down
docker volume rm brewery-scheduler_pgdata   # Name ggf. via `docker volume ls` prüfen
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env up -d
```

## Sicherheit (Testphase)

Basic-Auth vor der gesamten App (ein gemeinsames Testkonto), Datenbank und
Backend sind nicht von außen erreichbar, nur Caddy hat offene Ports.
**Vor echten Daten** (siehe PLANUNG.md §A): echter Login (Phase 5),
Backups extern spiegeln, und der öffentliche Codespace-Port wird wieder
privat.
