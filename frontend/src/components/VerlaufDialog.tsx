import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type { Sud, Tank, Verlaufseintrag } from "../api/types";
import { formatZahl, partnersOf, sudNumberLabel } from "../domain";

interface VerlaufDialogProps {
  /** Die Sude, um die es geht — bei einem gemischten Ausschanktank alle
   * darin enthaltenen. Ohne Angabe zeigt der Dialog alle Änderungen. */
  fuer?: Sud[];
  sude: Sud[];
  tanks: Tank[];
  onClose: () => void;
}

const AKTION: Record<Verlaufseintrag["action"], string> = {
  create: "angelegt",
  update: "geändert",
  delete: "gelöscht",
};

// Tabellennamen sind für Vincenz nichts wert.
const BEREICH: Record<string, string> = {
  sude: "Sud",
  tank_occupancy: "Tankbelegung",
  withdrawals: "Abgang",
  tanks: "Tank",
  recipes: "Rezept",
};

const FELD: Record<string, string> = {
  beer_style: "Sorte",
  brew_at: "Brauzeitpunkt",
  capacity_hl: "Größe",
  end_at: "Ende",
  kind: "Art",
  name: "Name",
  notes: "Notiz",
  stage: "Stufe",
  start_at: "Start",
  status: "Status",
  tank_id: "Tank",
  verbrauch_hl_pro_woche: "Ø-Ausschank",
  volume_hl: "Menge",
};

function feldName(feld: string): string {
  return FELD[feld] ?? feld;
}

/** Kennungen sagen niemandem etwas; Zahlen und Zeitpunkte schon. */
function wert(roh: unknown): string {
  if (roh === null || roh === undefined || roh === "") return "—";
  if (typeof roh === "number") return formatZahl(roh);
  if (typeof roh === "boolean") return roh ? "ja" : "nein";
  if (typeof roh === "object") return "…";
  const text = String(roh);
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-/.test(text)) return "…";
  const zeit = /^\d{4}-\d{2}-\d{2}T/.test(text) ? new Date(text) : null;
  if (zeit && !Number.isNaN(zeit.getTime())) {
    return zeit.toLocaleString("de-DE", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  return text;
}

function zeitpunkt(iso: string): string {
  return new Date(iso).toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Beim Anlegen und Löschen steht der ganze Zustand in `changes`; dort
 * sind nur wenige Felder aussagekräftig. */
function beschreibung(
  eintrag: Verlaufseintrag,
  auflösen: (feld: string, roh: unknown) => string,
): string[] {
  const felder = Object.entries(eintrag.changes);
  if (eintrag.action === "update") {
    return felder.map(([feld, aenderung]) => {
      const { alt, neu } = (aenderung ?? {}) as Record<string, unknown>;
      return `${feldName(feld)}: ${auflösen(feld, alt)} → ${auflösen(feld, neu)}`;
    });
  }
  return felder
    .filter(([feld]) => feld in FELD)
    .map(([feld, roh]) => `${feldName(feld)}: ${auflösen(feld, roh)}`);
}

export function VerlaufDialog({
  fuer,
  sude,
  tanks,
  onClose,
}: VerlaufDialogProps) {
  const [eintraege, setEintraege] = useState<Verlaufseintrag[] | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);
  const [nurDiese, setNurDiese] = useState(fuer !== undefined);

  // Ein Doppelsud führt seine Belegungen am Lead, kann aber selbst
  // geändert worden sein — der Partner gehört zum selben Bier.
  const ids = useMemo(
    () => [
      ...new Set(
        (fuer ?? [])
          .flatMap((s) => [s, ...partnersOf(s, sude)])
          .map((s) => s.id),
      ),
    ],
    [fuer, sude],
  );
  const schluessel = ids.join(",");

  // „Tank: …" hilft niemandem — der Name schon.
  const tankNamen = useMemo(
    () => new Map(tanks.map((t) => [t.id, t.name])),
    [tanks],
  );
  const auflösen = (feld: string, roh: unknown): string =>
    feld === "tank_id" ? (tankNamen.get(String(roh)) ?? wert(roh)) : wert(roh);

  useEffect(() => {
    let aktuell = true;
    setEintraege(null);
    setFehler(null);
    const abfrage = nurDiese
      ? Promise.all(ids.map((id) => api.listVerlauf(id))).then((listen) =>
          listen
            .flat()
            .sort((a, b) => b.at.localeCompare(a.at)),
        )
      : api.listVerlauf();
    abfrage
      .then((daten) => aktuell && setEintraege(daten))
      .catch((e) => aktuell && setFehler(e instanceof Error ? e.message : String(e)));
    return () => {
      aktuell = false;
    };
    // `ids` ist bei jedem Render neu; der Schlüssel hält die Abfrage stabil.
  }, [nurDiese, schluessel]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="dialog-backdrop" role="dialog" aria-label="Verlauf">
      <div className="dialog">
        <h2>Verlauf</h2>
        {fuer && nurDiese && (
          <p className="muted">
            {[...new Set(fuer.map((s) => sudNumberLabel(s, sude)))].join(" · ")}
          </p>
        )}

        {fuer && (
          <div className="zeitplan-segment">
            <button
              type="button"
              className={nurDiese ? "active" : ""}
              onClick={() => setNurDiese(true)}
            >
              {fuer.length > 1 ? "Diese Sude" : "Dieser Sud"}
            </button>
            <button
              type="button"
              className={nurDiese ? "" : "active"}
              onClick={() => setNurDiese(false)}
            >
              Alles
            </button>
          </div>
        )}

        {fehler && <p className="error">{fehler}</p>}
        {!fehler && eintraege === null && <p className="muted">Lädt …</p>}
        {eintraege !== null && eintraege.length === 0 && (
          <p className="muted">Noch keine Änderungen aufgezeichnet.</p>
        )}

        <ul className="verlauf">
          {(eintraege ?? []).map((eintrag) => (
            <li key={eintrag.id}>
              <div>
                <strong>{eintrag.actor}</strong> hat{" "}
                {BEREICH[eintrag.entity] ?? eintrag.entity}{" "}
                {AKTION[eintrag.action]}
                <span className="muted"> · {zeitpunkt(eintrag.at)}</span>
              </div>
              {beschreibung(eintrag, auflösen).map((zeile) => (
                <div className="muted" key={zeile}>
                  {zeile}
                </div>
              ))}
            </li>
          ))}
        </ul>

        <button type="button" onClick={onClose}>
          Schließen
        </button>
      </div>
    </div>
  );
}
