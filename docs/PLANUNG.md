# Planungsdokument — Stand 2026-08-04, Fragen an Stefan

Erstellt am Ende der zweiten Nachtschicht. Die ROADMAP-Phasen 1–3 sind
umgesetzt (Details unten); dieses Dokument sammelt, **was noch fehlt** und
**welche Entscheidungen nur du treffen kannst**. Die Fragen sind nach
Dringlichkeit gruppiert — A und B blockieren am meisten.

## Stand in einem Absatz

Kellerblick (Karten, alle Tap-Flows, Warnmarkierungen), freies Umdrücken mit
Warn- statt Blockier-Regeln, Fass-/Ausschank-Buchungen mit Restmengen,
Tankverwaltung (anlegen/ändern/ausblenden/sperren), frei anlegbare Standorte,
Rezeptverwaltung mit Versionen/Historie/Per-Sud-Abweichungen, neuer
Touch-Zeitplan (Tippen statt Ziehen), PWA mit Offline-Lesecache, Codespace
mit Selbstheilung/Watchdogs/Statusdateien. 71 Backend- und 40 Frontend-Tests.

## A. Betrieb & Daten — vor echten Daten zu klären

1. **Produktiv-Hosting.** Der Codespace ist eine Test-/Entwicklungsumgebung:
   die Datenbank ist **flüchtig** (jeder neue Codespace startet leer, GitHub
   löscht inaktive Codespaces nach ~30 Tagen), und nach ~30 min Inaktivität
   schläft alles. Sobald ihr echte Kellerdaten erfasst, braucht es festes
   Hosting (ROADMAP schlägt Azure vor, ~€30–40/Monat; eine kleine VM oder
   ein Mini-PC in der Brauerei ginge auch). **Frage: Wann willst du von
   „Testdaten wegwerfbar“ auf „echte Daten“ umstellen, und wo soll es
   laufen?**
2. **Port wieder privat.** Port 5173 ist aktuell öffentlich (deine Freigabe
   für den Feldtest). Vor echten Daten: wieder privat + echter Login
   (Entra ID, Phase 5) oder mindestens ein einfacher Passwortschutz.
3. **Backups.** Ab echten Daten: tägliche DB-Sicherung. Trivial beim
   Hosting-Umzug mitzulösen — vorher entscheiden, nicht nachher.
4. **Go-Live-Sudnummer.** Der interne globale Zähler kann beim Go-Live auf
   eure bestehende Zählung gesetzt werden (Skript existiert).
   **Frage: Bei welcher Nummer steht ihr?**

## B. Brauereimeister-Session — Daten, die nur ihr habt

5. **Echte Dauern je Rezept** (§2.7 sind Platzhalter). Neu: Ihr könnt sie
   jetzt **selbst im Rezepte-Tab pflegen** — jede Änderung wird eine neue
   Version mit Historie. Die Session kann also direkt im Tool stattfinden.
   Offen aus issue #2: gibt es **saisonale Unterschiede** (Sommer/Winter)?
6. **Fässer (issue #15).** Heute buchen wir nur „X hl in Fässer“. Fragen:
   (a) Aus welchen Stufen wird realistisch abgefüllt — nur Lager/Ausschank
   oder auch Gärtank? (b) Braucht ihr **Fass-Objekte** (Größen 30/50 l,
   Stückzahlen, Pfand) oder reicht das Volumen? (c) Sollen Fassabfüllungen
   später gegen Verkäufe (Phase 6) abgeglichen werden?
7. **Sud-Lebensende.** Wann gilt ein Sud als fertig („ausgeschenkt“)?
   Vorschlag: automatisch, sobald die Restmenge 0 erreicht — plus eine
   Archiv-Ansicht fürs Kellerbuch. **Passt das?**

## C. Offline & Mobile — nächster größerer Bauabschnitt

8. **Offline-Schreiben (issue #10).** Lesen offline funktioniert (PWA-Cache).
   Aktionen (Umdrücken, Fass, Anlegen) brauchen bei Funkloch eine
   **Warteschlange mit sichtbarem Status** und klarer Konfliktanzeige beim
   Nachspielen. Plan steht (TanStack Query v5, bewusst ohne Workbox
   Background Sync). **Frage: Wie oft seid ihr im Keller wirklich offline —
   ist das der nächste Bauabschnitt oder eher Komfort?**
9. **PWA aufs Homescreen.** „Zum Home-Bildschirm hinzufügen“ im Browser-Menü
   installiert die App mit Icon. Schon probiert? Wenn dort etwas hakt,
   bitte melden.

## D. Planung & Solver (Phase 4)

10. **Bedarfskalender.** Der Solver („Plane Pfingsten“) braucht als Eingabe,
    welches Bier wann in welchem Ausschanktank verfügbar sein muss. §2.6
    liefert die Pfingstziele (61 Sude / 915 hl). **Fragen: Soll der Solver
    zuerst den Pfingst-Hochlauf können oder den Normalbetrieb? Woher kommt
    der Normalbetriebs-Bedarf — Erfahrungswerte pro Woche?**
11. **Zeitplan-Feintuning.** Der neue Touch-Zeitplan verschiebt per
    ±1/±7-Tage-Knöpfen und Tank-Dropdown. Nach deinem Feldtest: reicht das,
    oder fehlt etwas (z. B. Wochenraster, Dauer ändern direkt im Zeitplan)?

## E. Kellerbuch & Pflichten

12. **Biersteuer-Export.** Ausschank- und Fass-Buchungen werden bereits
    einzeln mit Zeitstempel erfasst — die Datenbasis steht. **Frage: Welches
    Format braucht dein Steuerberater / Hauptzollamt (monatliche Summen je
    Steuerklasse? Excel/CSV?)** Dann baue ich den Export.
13. **Nutzer & Rollen.** Aktuell kann jeder mit Link alles. Ab wann braucht
    es getrennte Nutzer (Braumeister schreibend, andere nur lesend)? Hängt
    mit A.2/Phase 5 zusammen.

## F. M365-Integration (Phase 5) — braucht deine Vorarbeit

14. Entra-ID-App-Registrierung im Tenant (mache ich gern mit Anleitung,
    braucht aber deine Admin-Rechte), Teams-Tab, Excel-Export des Plans.
    **Frage: Wie wichtig ist Teams/Excel wirklich — vor oder nach dem
    Solver?**

## Meine Empfehlung zur Reihenfolge

1. **B5/B6 im Tool erledigen** (echte Rezeptdauern eintragen, Keg-Fragen
   beantworten) — kostet dich eine Stunde, entsperrt Warnqualität und
   Solver-Vorbereitung.
2. **E12 Biersteuer-Export** — klein, sofort nützlich, Daten liegen bereits.
3. **C8 Offline-Warteschlange** — der Mobile-Anker aus der ROADMAP.
4. **A1 Hosting-Umzug** — sobald ihr echt erfassen wollt; zusammen mit A2–A4.
5. **D10 Solver** — das große Ziel, braucht B5 und den Bedarfskalender.

## Erledigt (Referenz)

- Phase 1 Walking Skeleton ✓ · Phase 2 Track A Validierung ✓ (Regeln seit
  2026-08-03 als Warnungen statt Blockaden, Feldentscheidung) · Track B
  Kellerblick + PWA-Lesecache ✓ · Track C Touch-Zeitplan ✓ (2026-08-04)
- Phase 3 Rezeptverwaltung ✓ (2026-08-04): Versionen, Historie mit Diffs,
  Per-Sud-Abweichungen inkl. Termin- und Warnlogik
- Außerhalb der Roadmap aus Feldtests: freies Umdrücken, Fass/Ausschank-
  Buchungen mit Restmengen, Tankverwaltung + Standorte + Schloss,
  Warnmarkierungen, Codespace-Robustheit (Watchdogs, Statusdateien,
  Sync-Auto-Neustart, öffentlicher Testport)
- Offen aus Phase 2: **Offline-Mutations-Queue** (C8, issue #10)
