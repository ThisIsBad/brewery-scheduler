# Produktivbetrieb (MVP-Test mit Vincenz)

Stand 2026-08-05. Ein Server (Hetzner-Tendenz aus der Planungsrunde; jede
kleine Linux-VM mit Docker tut es), ein Stack, Basic-Auth davor. Die
Testdaten (Tanks, deine 10 Rezepte, Beispiel-Sude) werden beim ersten
Start automatisch eingespielt.

## Die laufende Installation (seit 2026-08-07)

- **https://sudplanung.entlaskeller.de** — Hetzner-VM `Sudplanung-Prod`,
  Ubuntu, Stack unter `/opt/brewery-scheduler`, Zertifikat von Caddy
  automatisch. Die Subdomain hängt als A-Record bei domainfactory neben
  der bestehenden Website; deren DNS-Einträge bleiben unberührt.
- **Update auf ein neues Release:** `git fetch --tags && git checkout vX.Y.Z`
  im Stack-Verzeichnis, dann `docker compose … up -d --build`.
- **Fallstrick aus dem ersten Go-Live:** Das Image installiert das Backend
  als Wheel. Neue nicht-Python-Dateien (Seed-Daten, Templates) müssen in
  `package-data` von `backend/pyproject.toml` stehen, sonst fehlen sie im
  Container, obwohl im Codespace alles läuft. Die CI prüft das seither.

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

## Eine Person hinzufügen

Jede Person bekommt ein eigenes Konto — das Änderungsprotokoll hängt am
Benutzernamen, ein gemeinsames Konto wäre dort wertlos.

```bash
cd /opt/brewery-scheduler
./deploy/benutzer.sh stefan          # fragt das Passwort verdeckt ab
./deploy/benutzer.sh --liste
./deploy/benutzer.sh --entfernen alex
```

Das Skript hasht das Passwort, trägt es in `deploy/.env` ein und startet
Caddy neu; die Datenbank bleibt unberührt. Ohne Passwort-Argument landet
es auch nicht in der Shell-Historie. Ein zweiter Aufruf mit demselben
Namen ändert das Passwort, statt einen zweiten Platz zu belegen.

Vier Plätze sind vorgesehen; für mehr je eine Zeile in `PLAETZE`
(`deploy/benutzer.sh`), `deploy/caddy-entrypoint.sh` und
`deploy/docker-compose.prod.yml` ergänzen.

## Läuft der neue Stand wirklich?

```bash
./deploy/stand.sh
```

Zeigt ausgechecktes Tag, Bauzeitpunkt der Oberfläche, ob die Cache-Regeln
im Container stecken und wie viele Konten es gibt. Das Deploy ruft es
selbst mit `--pruefen` auf — ein Ausrollvorgang, der nichts bewirkt hat,
wird damit rot statt still durchzulaufen.

**Wenn ein Handy trotzdem die alte Fassung zeigt:** Schuld ist der
Service Worker, der Anfragen abfängt, bevor sie den Server erreichen —
die Cache-Regeln greifen dort also nicht. Das Löschen des
Startbildschirm-Symbols entfernt ihn *nicht*. Wirksam ist nur:
Einstellungen → Safari → Erweitert → Website-Daten → den Eintrag der
Domain löschen. Danach im Profil den Bau-Zeitpunkt prüfen.

## Sicherheit (Testphase)

Basic-Auth vor der gesamten App (ein Konto je Person), Datenbank und
Backend sind nicht von außen erreichbar, nur Caddy hat offene Ports. Den
Benutzernamen setzt ausschließlich Caddy als Header `X-Authenticated-User`
— das Backend nimmt ihn nur deshalb für bare Münze, weil es keinen anderen
Weg von außen gibt.
**Vor echten Daten** (siehe PLANUNG.md §A): echter Login (Phase 5),
Backups extern spiegeln, und der öffentliche Codespace-Port wird wieder
privat.
