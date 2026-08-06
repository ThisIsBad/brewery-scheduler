"""Import Vincenz' Sudplanung 2026 (Sude 210-300) as seed data.

Source of truth is data/sudplan_2026.json, extracted from the workbook
"2026_Sudplanung.xlsx" via scripts/extract_sudplan_2026.py. The sheet is a
hand-maintained plan, so this loader repairs what it can and records what
it can't in each Sud's notes instead of failing:

- Tank chains whose Umdrück-Datum vor dem Braudatum liegt (nicht
  nachgepflegte Zeilen) werden an der ersten unstimmigen Stelle gekappt;
  das Gär-Ende fällt dann auf Braudatum + Rezept-Gärzeit.
- Doppelsude (gleiche Sorte, gleicher Gärtank, Braudaten ≤ 48 h
  auseinander) werden als Lead + Partner angelegt; der Lead trägt die
  Belegungen. Divergiert das Paar erst am Ausschankziel, entstehen zwei
  Ausschank-Belegungen mit den Einzelmengen (Split).
- Kollidiert eine Belegung trotzdem mit dem EXCLUDE-Constraint (der Plan
  enthält echte Überbuchungen), wird nur diese Belegung verworfen und am
  Sud vermerkt — genau solche Stellen soll die App sichtbar machen.

Mapping-Entscheidungen (Stefan, 2026-08-05): "Striezitank" ist der
Bergtank 120 hl; "Kitzmann groß/klein" sind Kitzmann hinten/vorne;
"Bergbier (Gisela)" ist das Festbier (belegt durch Sudblatt 210);
"Collab Sud 2026" läuft auf dem Rezept "Widder". "Fass" und
"Ausschank" sind keine Tanks — sie beenden die Kette (abgefüllt bzw.
direkt ausgeschenkt).
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    Recipe,
    Sud,
    SudStatus,
    Tank,
    TankOccupancy,
    TankStage,
    Withdrawal,
    WithdrawalKind,
)

DATA_FILE = Path(__file__).parent / "data" / "sudplan_2026.json"

SORTE_TO_RECIPE = {
    "Kellerbier Hell (Brudi)": "Brudi",
    "Kellerbier Hell (Sven)": "Sven",
    "Bergbier (Gisela)": "Gisela",
    "Bay. Dunkel (Enno)": "Enno",
    "Spezialsud (Schwesti)": "Schwesti",
    "Weizen (Fritz)": "Fritz",
    "Wiener Lager (Leopold)": "Leopold",
    "Rauchbier (Waltraut)": "Waltraut",
    "Weizenbock (Justus)": "Justus",
    "Collab Sud 2026": "Widder",
}

TANK_MAP = {
    "Kitzmann groß": "Kitzmann hinten",
    "Kitzmann klein": "Kitzmann vorne",
    "Bergtank": "Bergtank 100 hl",
    "Striezitank": "Bergtank 120 hl",
}

# Keine Tanks: "Fass" = abgefüllt, "Ausschank" = direkt ausgeschenkt.
CHAIN_END = {"Fass", "Ausschank"}

MERGE_WINDOW = timedelta(hours=48)

# „Bis leer" ist keine Planungsgröße: ein offenes Ausschank-Fenster würde
# jede spätere anderssortige Belegung im selben Tank blockieren (Sortenrein
# prüft Zeitfenster). Importierte Stationen enden deshalb beim Start der
# nächsten anderssortigen Station im Tank, spätestens nach dieser Dauer.
# Die Live-Buchungen der App arbeiten weiter mit „offen bis leer".
AUSSCHANK_PLAN_DAUER = timedelta(days=14)

# Standard-Sud (ROADMAP §2.1). Die Paar-Erkennung rechnet mit Plan-Mengen:
# zwei 15er passen in einen 30-hl-Gärtank, auch wenn die Sudhaus-Ausbeute
# laut Protokoll bei 16,x hl lag — gemessen wird vor den Gärverlusten.
STANDARD_SUD_HL = 15


def _dt(d: date, hour: int) -> datetime:
    return datetime.combine(d, time(hour), tzinfo=timezone.utc)


def _parse(iso: str | None) -> date | None:
    return date.fromisoformat(iso) if iso else None


class _Segment:
    def __init__(self, tank: Tank, start: datetime, end: datetime | None, synthetic: bool):
        self.tank = tank
        self.start = start
        self.end = end
        # synthetic = Ende stammt nicht aus dem Plan, sondern aus der
        # Rezept-Gärzeit (unstimmige Zeile) — solche Belegungen verlieren
        # bei Kollisionen zuerst.
        self.synthetic = synthetic


def _sanitize_chain(
    entry: dict, tanks: dict[str, Tank], recipe: Recipe
) -> tuple[list[_Segment], bool, list[str]]:
    """Kette in Segmente mit strikt aufsteigenden Zeiten übersetzen.

    Returns (segments, kegged, warnings). kegged = Kette endet im Fass
    oder direkt im Ausschank (kein weiterer Tank).
    """
    warnings: list[str] = []
    segments: list[_Segment] = []
    brew = _parse(entry["brew"])
    cursor = _dt(brew, 7)
    kegged = False

    for i, hop in enumerate(entry["chain"]):
        name = hop["tank"]
        if name in CHAIN_END:
            kegged = True
            break
        tank = tanks.get(TANK_MAP.get(name, name))
        if tank is None:
            warnings.append(f'Tank „{name}“ unbekannt — Kette dort gekappt')
            break
        until = _parse(hop["bis"])
        if until is not None and _dt(until, 12) > cursor:
            seg = _Segment(tank, cursor, _dt(until, 12), synthetic=False)
        elif until is None:
            # Offenes Ende: Ausschank bleibt offen, sonst Rezeptdauer.
            if tank.stage == TankStage.AUSSCHANK:
                seg = _Segment(tank, cursor, None, synthetic=False)
            else:
                days = recipe.storage_duration_days if i > 0 else recipe.fermentation_duration_days
                seg = _Segment(tank, cursor, cursor + timedelta(days=int(days)), synthetic=True)
        else:
            # Datum vor dem Start — Zeile wurde nicht nachgepflegt.
            warnings.append(
                f'Umdrücken „{name}“ am {until:%d.%m.} liegt vor dem Start — Kette gekappt'
            )
            if i == 0:
                seg = _Segment(
                    tank,
                    cursor,
                    cursor + timedelta(days=int(recipe.fermentation_duration_days)),
                    synthetic=True,
                )
                segments.append(seg)
            break
        segments.append(seg)
        if seg.end is None:
            break
        cursor = seg.end

    return segments, kegged, warnings


def _derive_status(
    segments: list[_Segment], kegged: bool, brew: date, today: date, versteuert: float | None
) -> SudStatus:
    now = _dt(today, 10)
    if brew > today:
        return SudStatus.PLANNED
    for seg in segments:
        if seg.start <= now and (seg.end is None or now < seg.end):
            if seg.tank.stage == TankStage.AUSSCHANK:
                return SudStatus.IN_AUSSCHANK
            if seg.tank.stage == TankStage.STORAGE:
                return SudStatus.STORING
            return SudStatus.FERMENTING
    if segments and now < segments[0].start:
        return SudStatus.PLANNED
    # Kette liegt komplett in der Vergangenheit. Wessen Ausschank-Fenster
    # vorbei ist, gilt als ausgeschenkt — auch wenn die versteuerte Menge
    # im Excel nie nachgetragen wurde.
    war_im_ausschank = bool(segments) and segments[-1].tank.stage == TankStage.AUSSCHANK
    if kegged or versteuert or war_im_ausschank:
        return SudStatus.SERVED
    return SudStatus.STORING  # steht rechnerisch noch im letzten Tank → Überfällig


def _plan_korrekturen(entries: list[dict]) -> None:
    """Handkorrekturen an bestätigten Excel-Fehlern — bewusst hier statt in
    der JSON, damit ein Extraktor-Rerun sie nicht überschreibt.

    Orientierung dazu (Stefan, 2026-08-06, KEINE harte Regel): Weizen,
    Spezialsude und Monatsbiere gehen so gut wie immer ins Fass;
    Kitzmann vorne ist praktisch ein reiner Kellerbier-Tank.
    """
    for entry in entries:
        if entry["global"] == 296:
            # K35: Weizen geht ins Fass, nicht nach Kitzmann vorne.
            entry["chain"] = [
                {"tank": "Fass", "bis": None}
                if hop["tank"] == "Kitzmann klein"
                else hop
                for hop in entry["chain"]
            ]
            zusatz = "Korrektur: ins Fass statt Kitzmann vorne (Stefan, 2026-08-06)"
            entry["note"] = f"{entry['note']} · {zusatz}" if entry["note"] else zusatz


def import_sudplan(session: Session, today: date | None = None) -> dict:
    """Legt die 91 Sude aus data/sudplan_2026.json an. Idempotenz besorgt
    der Aufrufer (seed überspringt bereits befüllte Datenbanken)."""

    today = today or date.today()
    entries = json.loads(DATA_FILE.read_text())
    _plan_korrekturen(entries)
    tanks = {t.name: t for t in session.query(Tank)}
    recipes = {r.name: r for r in session.query(Recipe)}

    stats = {"sude": 0, "paare": 0, "belegungen": 0, "verworfen": 0, "hinweise": 0}

    # Doppelsude: gleiche Sorte, gleicher Gärtank, Braudaten ≤ 48 h,
    # Gesamtmenge passt in den Tank. Der frühere Sud führt.
    entries.sort(key=lambda e: e["global"])
    batches: list[list[dict]] = []
    for entry in entries:
        prev = batches[-1][-1] if batches and len(batches[-1]) == 1 else None
        if prev is not None:
            same_tank = prev["chain"] and entry["chain"] and prev["chain"][0]["tank"] == entry["chain"][0]["tank"]
            tank = tanks.get(TANK_MAP.get(prev["chain"][0]["tank"], prev["chain"][0]["tank"])) if same_tank else None
            close = abs(
                _dt(_parse(entry["brew"]), 7) - _dt(_parse(prev["brew"]), 7)
            ) <= MERGE_WINDOW
            fits = tank is not None and 2 * STANDARD_SUD_HL <= tank.capacity_hl
            if prev["sorte"] == entry["sorte"] and same_tank and close and fits:
                batches[-1].append(entry)
                continue
        batches.append([entry])

    # Sortennummern zählen je (Sorte, Jahr) in Braureihenfolge über ALLE
    # Sude (Lead wie Partner) — wie es die App bei Neuanlagen auch tut.
    style_counters: dict[tuple[str, int], int] = {}

    prepared: list[tuple[list[dict], Recipe, list]] = []
    for batch in batches:
        recipe = recipes.get(SORTE_TO_RECIPE.get(batch[0]["sorte"], ""))
        if recipe is None:
            raise RuntimeError(
                f"Kein Rezept für Sorte {batch[0]['sorte']!r} (Sud {batch[0]['global']})"
            )
        prepared.append((batch, recipe, [_sanitize_chain(e, tanks, recipe) for e in batch]))

    # Offene Ausschank-Stationen bekommen ein Plan-Ende (siehe
    # AUSSCHANK_PLAN_DAUER): Start der nächsten anderssortigen Station im
    # selben Tank, spätestens Start + Plan-Dauer.
    starts_by_tank: dict[object, list[tuple[datetime, str]]] = {}
    for _batch, recipe, chains in prepared:
        for segments, _kegged, _warnings in chains:
            for seg in segments:
                if seg.tank.stage == TankStage.AUSSCHANK:
                    starts_by_tank.setdefault(seg.tank.id, []).append(
                        (seg.start, recipe.beer_style)
                    )
    for _batch, recipe, chains in prepared:
        for segments, _kegged, _warnings in chains:
            for seg in segments:
                if seg.end is None and seg.tank.stage == TankStage.AUSSCHANK:
                    fremde = [
                        start
                        for start, style in starts_by_tank.get(seg.tank.id, [])
                        if start > seg.start and style != recipe.beer_style
                    ]
                    cap = seg.start + AUSSCHANK_PLAN_DAUER
                    seg.end = min(min(fremde), cap) if fremde else cap
                    seg.synthetic = True

    # Stimmige Ketten zuerst einbuchen; synthetische Enden verlieren bei
    # Kollisionen (die späteren, gepflegten Daten sind die Wahrheit).
    def _coherence(item: tuple) -> tuple:
        batch, _recipe, chains = item
        return (1 if chains[0][2] else 0, batch[0]["global"])

    for batch, recipe, member_chains in sorted(prepared, key=_coherence):
        lead_entry = batch[0]
        segments, kegged, warnings = member_chains[0]

        # Paar-Feinheiten: gemeinsames Gär-Ende ist das spätere der beiden;
        # divergente Ausschank-Ziele werden zum Split mit Einzelmengen.
        split_segments: list[tuple[_Segment, float]] = []
        if len(batch) == 2:
            stats["paare"] += 1
            partner_segments, partner_kegged, partner_warnings = member_chains[1]
            kegged = kegged or partner_kegged
            warnings += [w for w in partner_warnings if w not in warnings]
            if segments and partner_segments:
                lead_end, partner_end = segments[0].end, partner_segments[0].end
                if lead_end and partner_end and partner_end > lead_end and not partner_segments[0].synthetic:
                    segments[0].end = partner_end
                    if len(segments) > 1:
                        segments[1].start = partner_end
            for pseg in partner_segments[1:]:
                if not any(s.tank.id == pseg.tank.id for s in segments):
                    split_segments.append((pseg, batch[1]["menge_hl"] or 15))

        batch_volume = sum(e["menge_hl"] or 15 for e in batch)
        brew_date = _parse(lead_entry["brew"])
        status = _derive_status(segments, kegged, brew_date, today, lead_entry["versteuert"])

        sude: list[Sud] = []
        for i, entry in enumerate(batch):
            e_brew = _parse(entry["brew"])
            year_key = (recipe.beer_style, e_brew.year)
            style_counters[year_key] = style_counters.get(year_key, 0) + 1
            note_parts = [f"Sudplan 2026: {entry['code']}"]
            if entry["stw"]:
                note_parts.append(f"Stammwürze {entry['stw'] * 100:.1f} %".replace(".", ","))
            if entry["versteuert"]:
                note_parts.append(f"versteuert lt. Plan {entry['versteuert']:g} hl")
            if entry["note"]:
                note_parts.append(entry["note"])
            if i == 0:
                note_parts += [f"Import: {w}" for w in warnings]
            sud = Sud(
                recipe_id=recipe.id,
                beer_style=recipe.beer_style,
                brew_at=_dt(e_brew, 7),
                brew_date=e_brew,
                status=status,
                brewmaster=entry["braumeister"] or "Vincenz",
                volume_hl=entry["menge_hl"] or 15,
                style_year_number=style_counters[year_key],
                global_number=entry["global"],
                notes=" · ".join(note_parts),
            )
            session.add(sud)
            sude.append(sud)
        session.flush()
        lead = sude[0]
        for partner in sude[1:]:
            partner.merged_into_sud_id = lead.id
        stats["sude"] += len(sude)
        stats["hinweise"] += len(warnings)

        # Ausschank-Belegungen tragen die Menge. Ohne Split ist das die
        # ganze Charge; beim Split (Paar mit getrennten Zielen) trägt jede
        # Seite ihre Einzelmenge.
        lead_share = (batch[0]["menge_hl"] or 15) if split_segments else batch_volume
        planned: list[tuple[_Segment, float | None]] = [
            (seg, lead_share if seg.tank.stage == TankStage.AUSSCHANK else None)
            for seg in segments
        ]
        planned += [
            (seg, vol if seg.tank.stage == TankStage.AUSSCHANK else None)
            for seg, vol in split_segments
        ]

        for seg, volume in planned:
            occupancy = TankOccupancy(
                sud_id=lead.id,
                tank_id=seg.tank.id,
                stage=seg.tank.stage,
                start_at=seg.start,
                end_at=seg.end,
                volume_hl=volume,
            )
            try:
                with session.begin_nested():
                    session.add(occupancy)
                    session.flush()
                stats["belegungen"] += 1
            except IntegrityError:
                stats["verworfen"] += 1
                clash = (
                    f"Import: Belegung {seg.tank.name} ab {seg.start:%d.%m.} kollidiert "
                    "mit einem anderen Sud — bitte im Zeitplan prüfen"
                )
                lead.notes = f"{lead.notes} · {clash}" if lead.notes else clash

        # Laufender Ausschank: bereits versteuerte Menge als Sammelbuchung,
        # damit der Kellerblick den echten Restbestand zeigt.
        if status == SudStatus.IN_AUSSCHANK and lead_entry["versteuert"]:
            tapped = next(
                (
                    s
                    for s, _vol in planned
                    if s.tank.stage == TankStage.AUSSCHANK
                ),
                None,
            )
            volume = min(lead_entry["versteuert"], batch_volume)
            if tapped is not None and volume > 0.05:
                session.add(
                    Withdrawal(
                        sud_id=lead.id,
                        tank_id=tapped.tank.id,
                        volume_hl=volume,
                        at=_dt(_parse(lead_entry["ausschank"]) or today, 18),
                        kind=WithdrawalKind.AUSSCHANK,
                        notes="Import: versteuert lt. Sudplanung",
                    )
                )

    # Neuanlagen zählen hinter dem Plan weiter (301, 302, …).
    max_global = max(e["global"] for e in entries)
    session.execute(
        text("SELECT setval('sud_global_seq', :next_value, false)"),
        {"next_value": max_global + 1},
    )
    return stats
