# Planungsdokument — Stand 2026-08-04 (nach Fragerunde mit Stefan)

**Entscheidungen aus der Fragerunde (2026-08-04):**

- Echte Daten erst **nächste Saison**; große Planung **im Dezember**.
- Hosting-Tendenz: **Hetzner** (kleiner Cloud-Server + Storage Box für
  nächtliche pg_dump-Backups, zusammen ~€8/Monat) statt Azure; die App
  bleibt **PWA** (keine native App). Final im Dezember.
- **Nächste Bauschritte in dieser Reihenfolge:** (1) Rezeptfelder — Malz,
  Hopfen (Gaben in Minuten), Hefe, Brauwerte (Stammwürze/IBU/Farbe) als
  Zielwerte, Mengen pro Standard-Sud 15 hl, Berechnungen später;
  (2) Fassabfüllung mit Stückzahlen je Größe (10/20/30/50 l), hl-Menge
  wird errechnet; (3) Blending-Modell (unten).
- **Blending/Sud-Ende (Vorschlag, noch nicht bestätigt):** Ausschank-
  Buchungen buchen auf den Tank und werden proportional auf die
  enthaltenen Sud-Anteile verteilt; ein Sud ist abgeschlossen, wenn sein
  Anteil überall 0 ist (auto-Archiv, Restschwund manuell ausbuchbar).
- **Biersteuer-Export**: vertagt (mehrere zu extrahierende Werte) →
  Dezember-Planung.
- **Zeitplan-Bedienung**: bleibt unverändert, bis Stefan am Handy
  getestet hat.

**Nachtrag 2026-08-04 (Bierrezepte.xlsx eingearbeitet):**

- Rezepte tragen jetzt den kompletten Brauzettel (Schüttung mit Mälzerei,
  Maischplan, Wasser, Hopfengaben mit Alpha-Säure und freiem Zeitpunkt,
  Kochzeit, Karbonisierung, Anstellhinweis). Sortennamen sind frei; die
  **10 echten Biere aus der Excel sind als Startdaten hinterlegt** —
  Wit und Leichtbier als „Frühere Biere" archiviert, wie in der Excel.
- **Platzhalter, bitte prüfen (Dezember/Brauereimeister):** Die Gär- und
  Lagerzeiten stehen NICHT in der Excel — alle 10 Rezepte tragen
  Platzhalterwerte (in den Notizen markiert). Für den **Weizenbock** ist
  „offene Gärung erforderlich" eine Annahme (Weizen-Familie) — bitte
  bestätigen oder im Rezept abwählen.
- **Brautag-Protokoll (offen):** Die Excel-Spalten „Läutern Von/Bis",
  „Gasstand", „Sudhausausbeute", „StwG %" sind **Protokolldaten je Sud**,
  kein Rezept. Kandidat für ein späteres „Brauprotokoll"-Feature am Sud
  (Dezember-Planung).

**Nachtrag 2026-08-05 (Feedbackrunde):**

- **Umdrücken**: nur noch Aufteilungszeilen — die separate Zieltank-Auswahl
  (Doppelanzeige) ist raus.
- **Fassgrößen**: 30 l vorerst aus den Dialogen (kaum verwendet); API
  bleibt tolerant, alte Buchungen gültig.
- **Blending ist sortenrein**: In einem Ausschanktank liegen nur Sude
  DERSELBEN Sorte — Mischen ist ein harter 409 (Umdrücken UND Planung),
  keine Warnung. Auch in CLAUDE.md als Domänenregel verankert.
- **Offline-Warteschlange**: bewusst einfach halten; Klärungsbedarf
  (Konflikt-Handling im Detail, Absicherung gegen Doppelbuchung bei
  verlorener Antwort) für eine eigene Runde notiert.

**Nachtrag 2026-08-06 (Vincenz-Tankwelt, bestätigt):**

- 22 Tanks mit echten Namen. Konvention: **Gär-/Lagertanks tragen
  Rufnamen** (Lisa … Yuri, Alva, Lovis; Vincenz … Fritz),
  **Ausschanktanks heißen nach ihrem Keller** (Bergtank 100/120 hl,
  Kitzmann vorne/hinten, Resenscheck, Striezi Keller 1–4). Typ und
  Größe kommen aus den Stammdaten — die App zeigt beides überall neben
  dem Namen; bewusst KEINE Typ-/Größen-Präfixe im Namen.
- Standorte = Keller: Schänke 4, Kitzmann Keller, Resenscheck Keller
  (nur Bergkirchweih), Striezi Keller.
- Die beiden 10-hl-Tanks sind Ausschanktanks. Sortenrein gilt damit
  überall dort, wo überhaupt gemischt werden kann — außerhalb des
  Ausschanks erzwingt die DB ohnehin Exklusivbelegung.
- Umbenennen können Stefan/Vincenz jederzeit selbst im Tanks-Tab.

**Nachtrag 2026-08-05 (Sudplanung 2026 übernommen):**

- Die 91 Sude (Nr. 210–300) aus `2026_Sudplanung.xlsx` sind Seed-Daten:
  `backend/scripts/extract_sudplan_2026.py` erzeugt
  `data/sudplan_2026.json`, `sudplan_2026.py` lädt sie beim Seeden.
  Aktualisiert Vincenz das Excel, Extraktor erneut laufen lassen und die
  JSON committen.
- **Globale Sudnummer** („Sud 285") ist jetzt Teil der Sud-Identität in
  API und UI; Neuanlagen zählen ab 301 weiter. Die Sorten-Nummer
  („Keller Hell 28/2026") bleibt daneben bestehen — Vincenz entscheidet
  später, ob das Format so bleibt.
- Mapping (Stefan, 2026-08-05): **„Striezitank" = Bergtank 120 hl**;
  „Kitzmann groß/klein" = Kitzmann hinten/vorne; „Bergtank" = Bergtank
  100 hl; **„Bergbier (Gisela)" = Festbier** (belegt durch Sudblatt 210);
  „Collab Sud 2026" läuft auf „Collab Widder"; „Fass"/„Ausschank" sind
  Ketten-Enden, keine Tanks.
- **Kellerbier gibt es zweimal**: Sorte „Kellerbier Hell" (Brudi) und als
  eigene Sorte „Kellerbier Hell Sven" (zusätzlich kalt nachgehopft) — zwei
  unterschiedliche Biere, ein Rezeptstrang je Sorte, sortenrein bleibt
  scharf. Neu angelegt: „Wiener Lager" (Leopold, Zutaten offen).
- **Tankevolution je Sud** (Stefan, 2026-08-06): typischerweise Gärtank →
  Lagertank → Ausschank/Fass, aber nicht immer — das Bier darf im Gärtank
  bleiben, der als Lagertank weiterdient (Gärtank hat zwei Abgänge zum
  Umdrücken: oberhalb und unterhalb der Hefe; der Lagertank nur einen).
  Der Umplanen-Dialog ist deshalb ein Ketten-Editor: Stationen mit freier
  Tankwahl über alle Typen, Ende = Start der nächsten, letzte Station
  optional offen; Stufe je Station aus dem gewählten Tank.
- **Sorte und Name sind getrennt** (Stefan, 2026-08-06): die Sorte trägt
  die volle Bezeichnung („Kellerbier Hell"), der Rezeptname ist nur der
  Spitzname („Brudi", „Fritz", „Gisela" …) — Anzeige überall
  „Kellerbier Hell 17/2026 · Brudi". Gemischte Ausschank-Karten zeigen
  EINE Zeile pro Bier (Sorte · Name, Sudnummern als Herkunft,
  Gesamtmenge) statt einer Sud-Aufteilung — vermischt ist vermischt.
- Import-Prinzip: reparieren was geht, den Rest **am Sud vermerken**
  statt scheitern — 13 nicht nachgepflegte Zeilen („Kette gekappt"),
  3 echte Plan-Überbuchungen (Wanda 285 vs. 298, Lisa 297 vs. 292,
  Evelyn 250+251) stehen als Notiz am Sud und tauchen im Zeitplan als
  Lücke auf. Ausschank älter als 3 Wochen gilt als leer (abgeschlossen).

**Was aus Rezeptwerten errechenbar wäre (Aufstellung für Stefan, 2026-08-05):**

| Rechnung | Braucht | Stand |
|---|---|---|
| Schüttungsanteile in % (wie Excel-Spalte) | nur kg je Malz | Daten komplett — nur Anzeige ergänzen |
| Einkaufslisten (kg je Malz/Mälzerei, g je Hopfensorte über geplante Sude) | Rezepte + geplante Sude | Daten komplett |
| Soll-IBU je Rezept (Tinseth) + Vergleich mit IBU-Ziel | g, % Alpha (da), Kochzeit der Gabe (aus Zeitpunkt-Text ableitbar), Stammwürze (da), Ausschlagmenge (da) | machbar; Whirlpool-/Kaltgaben mit Restausnutzung angenähert |
| Hopfen-Umrechnung bei neuer Charge (gleiche Bittere, neues % Alpha) | % Alpha alt + neu | machbar, je Gabe: g·α_alt/α_neu |
| Bierfarbe (EBC, Morey-Näherung) | EBC-Wert **je Malz** | Feld je Malz fehlt noch (kleine Ergänzung) |
| Stammwürze-Plausibilität („275 kg auf 15,5 hl ⇒ ~11,9 °P") | Schüttung (da), Menge (da), Sudhausausbeute in % | Ausbeute als Brauereiwert einmalig pflegen — oder aus Brauprotokoll |
| Tatsächliche Sudhausausbeute | Pfanne-voll-Menge + StW vom Brautag | braucht Brauprotokoll (Dezember) |
| Alkoholgehalt, Vergärungsgrad | Restextrakt-Messung je Sud | braucht Brauprotokoll |
| Biersteuer-Basis (°P × Mengen, Fass/Ausschank getrennt) | vorhandene Buchungen + °P | Daten laufen schon auf; Auswertung vertagt (Dezember) |
| Fass-Bestandsabgleich | Stückzahlen je Buchung (da) | Phase 6 |

---

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
