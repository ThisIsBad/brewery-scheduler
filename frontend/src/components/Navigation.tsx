import { useEffect, useState } from "react";

import { api } from "../api/client";

export type View =
  | "kellerblick"
  | "zeitplan"
  | "einkauf"
  | "tanks"
  | "rezepte"
  | "verlauf";

/** Was Vincenz täglich braucht, liegt unten am Daumen; Stammdaten und
 * Protokoll stecken hinter „Mehr" (Stefan, 2026-08-07). */
const UNTEN: { view: View; label: string }[] = [
  { view: "kellerblick", label: "Kellerblick" },
  { view: "zeitplan", label: "Zeitplan" },
  { view: "einkauf", label: "Einkauf" },
];

const IM_MEHR: { view: View; label: string }[] = [
  { view: "tanks", label: "Tanks" },
  { view: "rezepte", label: "Rezepte" },
  { view: "verlauf", label: "Verlauf" },
];

export const VIEW_TITEL: Record<View, string> = {
  kellerblick: "Kellerblick",
  zeitplan: "Zeitplan",
  einkauf: "Einkauf",
  tanks: "Tanks",
  rezepte: "Rezepte",
  verlauf: "Verlauf",
};

interface NavigationProps {
  view: View;
  onView: (view: View) => void;
}

export function Navigation({ view, onView }: NavigationProps) {
  const [mehrOffen, setMehrOffen] = useState(false);
  const stecktImMehr = IM_MEHR.some((e) => e.view === view);

  return (
    <>
      {mehrOffen && (
        <div className="dialog-backdrop" role="dialog" aria-label="Mehr">
          <div className="dialog">
            <h2>Mehr</h2>
            {IM_MEHR.map((e) => (
              <button
                key={e.view}
                type="button"
                className={view === e.view ? "menue-eintrag aktiv" : "menue-eintrag"}
                onClick={() => {
                  onView(e.view);
                  setMehrOffen(false);
                }}
              >
                {e.label}
              </button>
            ))}
            <button type="button" onClick={() => setMehrOffen(false)}>
              Schließen
            </button>
          </div>
        </div>
      )}

      <nav className="bottom-nav" aria-label="Ansicht">
        {UNTEN.map((e) => (
          <button
            key={e.view}
            type="button"
            className={view === e.view ? "active" : ""}
            aria-current={view === e.view ? "page" : undefined}
            onClick={() => onView(e.view)}
          >
            {e.label}
          </button>
        ))}
        <button
          type="button"
          className={stecktImMehr ? "active" : ""}
          aria-current={stecktImMehr ? "page" : undefined}
          onClick={() => setMehrOffen(true)}
        >
          Mehr
        </button>
      </nav>
    </>
  );
}

function bauZeit(): string {
  // Gesetzt wird der Wert beim Bauen (vite.config.ts). In Tests und bei
  // einem Bau ohne die Definition gibt es ihn nicht — dann lieber
  // „unbekannt" als ein Absturz im Profil.
  const roh = typeof __BAU_ZEIT__ === "string" ? __BAU_ZEIT__ : "";
  const zeit = new Date(roh);
  return Number.isNaN(zeit.getTime())
    ? "unbekannt"
    : zeit.toLocaleString("de-DE", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

export function Profil() {
  const [offen, setOffen] = useState(false);
  const [benutzer, setBenutzer] = useState<string | null>(null);

  useEffect(() => {
    let aktuell = true;
    api
      .ich()
      .then((antwort) => aktuell && setBenutzer(antwort.benutzer))
      .catch(() => {});
    return () => {
      aktuell = false;
    };
  }, []);

  return (
    <>
      <button
        type="button"
        className="profil"
        aria-label={benutzer ? `Angemeldet als ${benutzer}` : "Profil"}
        onClick={() => setOffen(true)}
      >
        <svg
          viewBox="0 0 24 24"
          width="22"
          height="22"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="8" r="3.5" />
          <path d="M5 20c0-3.9 3.1-7 7-7s7 3.1 7 7" />
        </svg>
      </button>

      {offen && (
        <div className="dialog-backdrop" role="dialog" aria-label="Profil">
          <div className="dialog">
            <h2>Angemeldet</h2>
            <p className="beer">{benutzer ?? "unbekannt"}</p>
            <p className="muted">
              Dein Name steht an jeder Änderung im Verlauf.
            </p>
            {/* Basic-Auth kennt kein Abmelden — genau deshalb tippt man
                hier: um zu prüfen, an welchem Konto das Gerät hängt. */}
            <p className="muted">
              Für ein anderes Konto alle Fenster der App schließen und neu
              öffnen — die Anmeldung merkt sich der Browser dauerhaft.
            </p>
            {/* Ohne Datum lässt sich am Gerät nicht sagen, ob es den
                ausgerollten Stand hat. */}
            <p className="muted">Stand der App: {bauZeit()}</p>
            <button type="button" onClick={() => setOffen(false)}>
              Schließen
            </button>
          </div>
        </div>
      )}
    </>
  );
}
