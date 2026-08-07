import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { Sud, Tank, Verlaufseintrag } from "../api/types";
import { formatZahl, sudNumberLabel } from "../domain";

interface VerlaufProps {
  sude: Sud[];
  tanks: Tank[];
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
    weekday: "short",
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

/** Tag als Überschrift: „Wer hat gestern was gemacht" ist die Frage,
 * mit der man hier hereinkommt. */
function tag(iso: string): string {
  return new Date(iso).toLocaleDateString("de-DE", {
    weekday: "long",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

export function Verlauf({ sude, tanks }: VerlaufProps) {
  const [eintraege, setEintraege] = useState<Verlaufseintrag[] | null>(null);
  const [fehler, setFehler] = useState<string | null>(null);

  useEffect(() => {
    let aktuell = true;
    api
      .listVerlauf()
      .then((daten) => aktuell && setEintraege(daten))
      .catch(
        (e) => aktuell && setFehler(e instanceof Error ? e.message : String(e)),
      );
    return () => {
      aktuell = false;
    };
  }, []);

  const tankNamen = new Map(tanks.map((t) => [t.id, t.name]));
  const auflösen = (feld: string, roh: unknown): string =>
    feld === "tank_id" ? (tankNamen.get(String(roh)) ?? wert(roh)) : wert(roh);

  // Ohne Sud-Karte drumherum muss jede Zeile selbst sagen, worum es geht.
  const sudLabel = (sudId: string | null): string | null => {
    if (!sudId) return null;
    const sud = sude.find((s) => s.id === sudId);
    return sud ? sudNumberLabel(sud, sude) : null;
  };

  let letzterTag: string | null = null;

  return (
    <div className="verlauf-seite">
      <h2>Verlauf</h2>
      <p className="muted">
        Alle Änderungen, neueste zuerst — wer hat wann was gemacht.
      </p>

      {fehler && <p className="error">{fehler}</p>}
      {!fehler && eintraege === null && <p className="empty">lade …</p>}
      {eintraege !== null && eintraege.length === 0 && (
        <p className="empty">Noch keine Änderungen aufgezeichnet.</p>
      )}

      <ul className="verlauf">
        {(eintraege ?? []).map((eintrag) => {
          const heute = tag(eintrag.at);
          const neuerTag = heute !== letzterTag;
          letzterTag = heute;
          const label = sudLabel(eintrag.sud_id);
          return (
            <li key={eintrag.id}>
              {neuerTag && <h3>{heute}</h3>}
              <div>
                <strong>{eintrag.actor}</strong> hat{" "}
                {BEREICH[eintrag.entity] ?? eintrag.entity}{" "}
                {AKTION[eintrag.action]}
                {label ? ` — ${label}` : ""}
                <span className="muted"> · {zeitpunkt(eintrag.at)}</span>
              </div>
              {beschreibung(eintrag, auflösen).map((zeile) => (
                <div className="muted" key={zeile}>
                  {zeile}
                </div>
              ))}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
