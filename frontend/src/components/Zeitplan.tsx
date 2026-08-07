import { useEffect, useMemo, useRef, useState } from "react";

import type { Occupancy, Sud, Tank } from "../api/types";
import { STAGE_LABEL, formatHl, globalSudLabel, partnersOf, sudNumberLabel } from "../domain";

interface ZeitplanProps {
  tanks: Tank[];
  sude: Sud[];
  onMoveOccupancy: (
    sudId: string,
    occupancyId: string,
    nextTankId: string,
    nextStartMs: number,
  ) => void;
  /** Dauer ändern: nur end_at wandert, der Start bleibt. */
  onResizeOccupancy: (
    sudId: string,
    occupancyId: string,
    nextEndMs: number,
  ) => void;
}

// Fällt nur noch als Notnagel an, wenn ein Bier (noch) keine Farbe hat —
// die eigentliche Farbe pflegt der Rezepte-Tab (sud.recipe.farbe).
const FALLBACK_COLOR = "#888";

/** Lesbare Textfarbe auf der Bierfarbe (einfache Luminanz-Schwelle). */
function textColorFor(hex: string): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) return "#fff";
  const n = parseInt(m[1], 16);
  const luminanz =
    (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) /
    255;
  return luminanz > 0.62 ? "#333" : "#fff";
}

const DAY_MS = 86_400_000;

// Die drei Zeiträume, in denen Vincenz denkt (Stefan, 2026-08-06):
// Woche fürs Tagesgeschäft, Monat als Standard, Jahr für die Saison.
// minBlock hält Blöcke tippbar, ohne die Jahresansicht zu fluten.
type Zeitraum = "woche" | "monat" | "jahr";
const ZEITRAUM_CONFIG: Record<Zeitraum, { dayWidth: number; minBlock: number }> = {
  woche: { dayWidth: 64, minBlock: 32 },
  monat: { dayWidth: 13, minBlock: 16 },
  jahr: { dayWidth: 3, minBlock: 8 },
};
const ZEITRAUM_LABEL: Record<Zeitraum, string> = {
  woche: "Woche",
  monat: "Monat",
  jahr: "Jahr",
};
const PAST_DAYS = 7;

interface Selected {
  sud: Sud;
  occ: Occupancy;
}

/** Touch-first planning timeline (Track C): tap a block to select it,
 * then move it with the day buttons or re-tank it via the dropdown —
 * no drag geometry, so it works with gloves in the cellar. */
export function Zeitplan({
  tanks,
  sude,
  onMoveOccupancy,
  onResizeOccupancy,
}: ZeitplanProps) {
  const [zeitraum, setZeitraum] = useState<Zeitraum>("monat");
  // Jahresauswahl: die Jahre kommen aus den Daten — sobald die Historie
  // der Vorjahre eingepflegt ist, tauchen sie hier automatisch auf.
  const heutigesJahr = new Date().getFullYear();
  const [jahr, setJahr] = useState(heutigesJahr);
  // Zwei Sichten (Stefan, 2026-08-06): Tanksicht = Zeile je Tank (wo ist
  // was frei), Sudsicht = Zeile je Charge (die Tankevolution eines Suds
  // als Kette lesbar). Auswahl und Aktionsleiste sind identisch.
  const [sicht, setSicht] = useState<"tanks" | "sude">("tanks");
  const [selected, setSelected] = useState<Selected | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const { dayWidth, minBlock } = ZEITRAUM_CONFIG[zeitraum];

  const jahre = useMemo(() => {
    const set = new Set(sude.map((s) => Number(s.brew_date.slice(0, 4))));
    set.add(heutigesJahr);
    return [...set].sort((a, b) => a - b);
  }, [sude, heutigesJahr]);

  // Woche/Monat: rollierendes Fenster um heute — in einem anderen Jahr ab
  // dessen 1. Januar. Jahr: das gewählte Kalenderjahr komplett.
  const { windowStart, totalDays } = useMemo(() => {
    if (zeitraum === "jahr") {
      const anfang = new Date(jahr, 0, 1).getTime();
      const ende = new Date(jahr + 1, 0, 1).getTime();
      return {
        windowStart: anfang,
        totalDays: Math.round((ende - anfang) / DAY_MS),
      };
    }
    const future = zeitraum === "woche" ? 28 : 60;
    const heute = new Date();
    heute.setHours(0, 0, 0, 0);
    const windowStart =
      jahr === heute.getFullYear()
        ? heute.getTime() - PAST_DAYS * DAY_MS
        : new Date(jahr, 0, 1).getTime();
    return { windowStart, totalDays: PAST_DAYS + future };
  }, [zeitraum, jahr]);

  const days = useMemo(
    () =>
      Array.from({ length: totalDays }, (_, i) => new Date(windowStart + i * DAY_MS)),
    [windowStart, totalDays],
  );

  // Deactivated tanks keep their row only while history references them.
  const rows = useMemo(
    () =>
      tanks.filter(
        (t) =>
          t.active ||
          sude.some((s) => s.occupancies.some((o) => o.tank_id === t.id)),
      ),
    [tanks, sude],
  );

  const sudById = useMemo(() => new Map(sude.map((s) => [s.id, s])), [sude]);
  const tankById = useMemo(() => new Map(tanks.map((t) => [t.id, t])), [tanks]);
  const blocksByTank = useMemo(() => {
    const map = new Map<string, { sud: Sud; occ: Occupancy }[]>();
    for (const sud of sude) {
      for (const occ of sud.occupancies) {
        const list = map.get(occ.tank_id) ?? [];
        list.push({ sud, occ });
        map.set(occ.tank_id, list);
      }
    }
    return map;
  }, [sude]);

  // Sudsicht: eine Zeile je Charge mit Belegung im sichtbaren Fenster,
  // aufsteigend nach globaler Sudnummer — beim Doppelsud zählt die
  // niedrigere Nummer des Paars (Stefan, 2026-08-06).
  const windowEnd = windowStart + totalDays * DAY_MS;
  const sudRows = useMemo(() => {
    const minGlobal = (s: Sud) =>
      Math.min(s.global_number, ...partnersOf(s, sude).map((p) => p.global_number));
    return sude
      .filter((s) => s.merged_into_sud_id === null && s.occupancies.length > 0)
      .map((s) => ({
        sud: s,
        occs: [...s.occupancies].sort(
          (a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime(),
        ),
      }))
      .filter(({ occs }) =>
        occs.some((o) => {
          const start = new Date(o.start_at).getTime();
          const end = o.end_at ? new Date(o.end_at).getTime() : windowEnd;
          return start < windowEnd && end > windowStart;
        }),
      )
      .sort((a, b) => minGlobal(a.sud) - minGlobal(b.sud));
  }, [sude, windowStart, windowEnd]);

  const scrollToHeute = () => {
    const el = scrollRef.current;
    if (!el) return;
    const heuteIndex = Math.floor((Date.now() - windowStart) / DAY_MS);
    el.scrollLeft = Math.max(0, (heuteIndex - 1) * dayWidth);
  };

  // Land on "today" when the plan opens; the past is one swipe away.
  useEffect(() => {
    scrollToHeute();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dayWidth, windowStart]);

  const nowOffset = ((Date.now() - windowStart) / DAY_MS) * dayWidth;

  const moveSelected = (deltaDays: number) => {
    if (!selected) return;
    const nextStart =
      new Date(selected.occ.start_at).getTime() + deltaDays * DAY_MS;
    onMoveOccupancy(selected.sud.id, selected.occ.id, selected.occ.tank_id, nextStart);
  };

  // Dauer ändern (Stefan, 2026-08-05: bewusst Start ODER Dauer wählen):
  // nur end_at wandert, der Start bleibt — z. B. Lagerung um eine Woche
  // verlängern.
  const resizeSelected = (deltaDays: number) => {
    if (!selected?.occ.end_at) return;
    const nextEnd = new Date(selected.occ.end_at).getTime() + deltaDays * DAY_MS;
    if (nextEnd <= new Date(selected.occ.start_at).getTime()) return;
    onResizeOccupancy(selected.sud.id, selected.occ.id, nextEnd);
  };

  const canResize = (deltaDays: number): boolean => {
    if (!selected?.occ.end_at) return false;
    return (
      new Date(selected.occ.end_at).getTime() + deltaDays * DAY_MS >
      new Date(selected.occ.start_at).getTime()
    );
  };

  const retankSelected = (tankId: string) => {
    if (!selected || tankId === "") return;
    onMoveOccupancy(
      selected.sud.id,
      selected.occ.id,
      tankId,
      new Date(selected.occ.start_at).getTime(),
    );
  };

  // Keep the selection alive across moves: the schedule PUT replaces the
  // occupancy rows wholesale, so the ids change — refind by stage and
  // nearest start so "+1 Tag, +1 Tag, +1 Tag" works without re-tapping.
  useEffect(() => {
    if (!selected) return;
    const fresh = sudById.get(selected.sud.id);
    if (!fresh) {
      setSelected(null);
      return;
    }
    const byId = fresh.occupancies.find((o) => o.id === selected.occ.id);
    const oldStart = new Date(selected.occ.start_at).getTime();
    const next =
      byId ??
      fresh.occupancies
        .filter((o) => o.stage === selected.occ.stage)
        .sort(
          (a, b) =>
            Math.abs(new Date(a.start_at).getTime() - oldStart) -
            Math.abs(new Date(b.start_at).getTime() - oldStart),
        )[0];
    if (!next) {
      setSelected(null);
      return;
    }
    if (next !== selected.occ || fresh !== selected.sud) {
      setSelected({ sud: fresh, occ: next });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sude]);

  const renderBlock = (
    sud: Sud,
    occ: Occupancy,
    label: string,
    kettenKlasse = "",
  ) => {
    const start = new Date(occ.start_at).getTime();
    const end = occ.end_at ? new Date(occ.end_at).getTime() : windowEnd;
    const left = ((start - windowStart) / DAY_MS) * dayWidth;
    const width = Math.max(((end - start) / DAY_MS) * dayWidth, minBlock);
    if (left + width < 0 || left > totalDays * dayWidth) return null;
    const isSelected = selected?.occ.id === occ.id && selected.sud.id === sud.id;
    const warned = (sud.warnings?.length ?? 0) > 0;
    return (
      <button
        type="button"
        key={occ.id}
        className={
          "zeitplan-block" +
          (isSelected ? " selected" : "") +
          (warned ? " warn" : "") +
          kettenKlasse
        }
        style={{
          left: Math.max(left, 0),
          width: left < 0 ? width + left : width,
          background: warned ? undefined : sud.recipe.farbe ?? FALLBACK_COLOR,
          color: warned
            ? undefined
            : textColorFor(sud.recipe.farbe ?? FALLBACK_COLOR),
        }}
        aria-label={label}
        onClick={() => setSelected(isSelected ? null : { sud, occ })}
      >
        {zeitraum === "jahr" ? null : label}
      </button>
    );
  };

  return (
    <div className="zeitplan">
      <div className="zeitplan-toolbar">
        <span className="zeitplan-gruppe">Zeitraum</span>
        <span className="zeitplan-segment">
          {(Object.keys(ZEITRAUM_CONFIG) as Zeitraum[]).map((z) => (
            <button
              type="button"
              key={z}
              className={zeitraum === z ? "active" : ""}
              aria-pressed={zeitraum === z}
              onClick={() => setZeitraum(z)}
            >
              {ZEITRAUM_LABEL[z]}
            </button>
          ))}
        </span>
        <select
          className="zeitplan-jahr"
          aria-label="Jahr"
          value={jahr}
          onChange={(e) => setJahr(Number(e.target.value))}
        >
          {jahre.map((j) => (
            <option key={j} value={j}>
              {j}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => {
            setJahr(heutigesJahr);
            scrollToHeute();
          }}
        >
          Heute
        </button>
        <span className="zeitplan-gruppe">Plantyp</span>
        <span className="zeitplan-segment">
          <button
            type="button"
            className={sicht === "tanks" ? "active" : ""}
            aria-pressed={sicht === "tanks"}
            onClick={() => setSicht("tanks")}
          >
            Tanks
          </button>
          <button
            type="button"
            className={sicht === "sude" ? "active" : ""}
            aria-pressed={sicht === "sude"}
            onClick={() => setSicht("sude")}
          >
            Sude
          </button>
        </span>
      </div>

      <div className="zeitplan-scroll" ref={scrollRef}>
        <div
          className="zeitplan-grid"
          style={{ width: totalDays * dayWidth + 140 }}
        >
          <div className="zeitplan-header">
            <div className="zeitplan-tanklabel" />
            <div className="zeitplan-days" style={{ width: totalDays * dayWidth }}>
              {days.map((d, i) => {
                if (zeitraum === "jahr" && d.getDate() !== 1) return null;
                return (
                  <div
                    key={d.getTime()}
                    className={
                      zeitraum !== "jahr" &&
                      (d.getDay() === 0 || d.getDay() === 6)
                        ? "zeitplan-day weekend"
                        : "zeitplan-day"
                    }
                    style={{
                      width: zeitraum === "jahr" ? 40 : dayWidth,
                      left: i * dayWidth,
                    }}
                  >
                    {zeitraum === "jahr"
                      ? d.toLocaleDateString("de-DE", { month: "short" })
                      : zeitraum === "woche" ||
                          d.getDate() === 1 ||
                          d.getDay() === 1
                        ? `${d.getDate()}.${d.getMonth() + 1}.`
                        : ""}
                  </div>
                );
              })}
            </div>
          </div>

          {sicht === "tanks" &&
            rows.map((tank) => (
              <div className="zeitplan-row" key={tank.id}>
                <div className="zeitplan-tanklabel">
                  <strong>{tank.name}</strong>
                  <span className="muted">
                    {STAGE_LABEL[tank.stage]} · {formatHl(tank.capacity_hl)}
                  </span>
                </div>
                <div
                  className="zeitplan-track"
                  style={{ width: totalDays * dayWidth }}
                >
                  {nowOffset >= 0 && nowOffset <= totalDays * dayWidth && (
                    <div className="zeitplan-now" style={{ left: nowOffset }} />
                  )}
                  {/* Auswahl hebt die ganze Kette des Suds hervor — so ist
                      die Bewegung über mehrere Tanks auch hier lesbar. */}
                  {(blocksByTank.get(tank.id) ?? []).map(({ sud, occ }) =>
                    renderBlock(
                      sud,
                      occ,
                      sudNumberLabel(sud, sude),
                      !selected
                        ? ""
                        : selected.sud.id === sud.id
                          ? selected.occ.id === occ.id
                            ? ""
                            : " kette"
                          : " fremd",
                    ),
                  )}
                </div>
              </div>
            ))}
          {sicht === "sude" &&
            sudRows.map(({ sud, occs }) => (
              <div className="zeitplan-row" key={sud.id}>
                <div className="zeitplan-tanklabel">
                  <strong>{sudNumberLabel(sud, sude)}</strong>
                  <span className="muted">
                    {sud.recipe.name} · {globalSudLabel(sud, sude)}
                  </span>
                </div>
                <div
                  className="zeitplan-track"
                  style={{ width: totalDays * dayWidth }}
                >
                  {nowOffset >= 0 && nowOffset <= totalDays * dayWidth && (
                    <div className="zeitplan-now" style={{ left: nowOffset }} />
                  )}
                  {occs.map((occ) =>
                    renderBlock(
                      sud,
                      occ,
                      tankById.get(occ.tank_id)?.name ?? "?",
                    ),
                  )}
                </div>
              </div>
            ))}
        </div>
      </div>

      {selected && (
        <div className="zeitplan-actionbar" role="toolbar" aria-label="Sud verschieben">
          <div className="zeitplan-actioninfo">
            <strong>
              {sudNumberLabel(selected.sud, sude)} · {selected.sud.recipe.name}
            </strong>
            <span className="muted">
              {globalSudLabel(selected.sud, sude)} ·{" "}
              {STAGE_LABEL[selected.occ.stage]} ·{" "}
              {new Date(selected.occ.start_at).toLocaleDateString("de-DE")}
              {selected.occ.end_at
                ? ` – ${new Date(selected.occ.end_at).toLocaleDateString("de-DE")} (${Math.round(
                    (new Date(selected.occ.end_at).getTime() -
                      new Date(selected.occ.start_at).getTime()) /
                      DAY_MS,
                  )} Tage)`
                : " – offen"}
            </span>
          </div>
          <div className="zeitplan-actions">
            <span className="zeitplan-gruppe">Start</span>
            <button type="button" aria-label="Start −7 Tage" onClick={() => moveSelected(-7)}>
              −7
            </button>
            <button type="button" aria-label="Start −1 Tag" onClick={() => moveSelected(-1)}>
              −1
            </button>
            <button type="button" aria-label="Start +1 Tag" onClick={() => moveSelected(1)}>
              +1
            </button>
            <button type="button" aria-label="Start +7 Tage" onClick={() => moveSelected(7)}>
              +7
            </button>
          </div>
          {selected.occ.end_at && (
            <div className="zeitplan-actions">
              <span className="zeitplan-gruppe">Dauer</span>
              <button
                type="button"
                aria-label="Dauer −7 Tage"
                disabled={!canResize(-7)}
                onClick={() => resizeSelected(-7)}
              >
                −7
              </button>
              <button
                type="button"
                aria-label="Dauer −1 Tag"
                disabled={!canResize(-1)}
                onClick={() => resizeSelected(-1)}
              >
                −1
              </button>
              <button
                type="button"
                aria-label="Dauer +1 Tag"
                onClick={() => resizeSelected(1)}
              >
                +1
              </button>
              <button
                type="button"
                aria-label="Dauer +7 Tage"
                onClick={() => resizeSelected(7)}
              >
                +7
              </button>
            </div>
          )}
          <div className="zeitplan-actions">
            <select
              aria-label="Tank wechseln"
              value={selected.occ.tank_id}
              onChange={(e) => retankSelected(e.target.value)}
            >
              {tanks
                .filter(
                  (t) =>
                    (t.active && t.stage === selected.occ.stage) ||
                    t.id === selected.occ.tank_id,
                )
                .map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
            </select>
            <button
              type="button"
              className="secondary"
              onClick={() => setSelected(null)}
            >
              Schließen
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
