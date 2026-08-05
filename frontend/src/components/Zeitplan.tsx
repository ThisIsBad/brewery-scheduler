import { useEffect, useMemo, useRef, useState } from "react";

import type { Occupancy, Sud, Tank } from "../api/types";
import { STAGE_LABEL, sudNumberLabel } from "../domain";

interface ZeitplanProps {
  tanks: Tank[];
  sude: Sud[];
  onMoveOccupancy: (
    sudId: string,
    occupancyId: string,
    nextTankId: string,
    nextStartMs: number,
  ) => void;
}

const STYLE_COLOR: Record<string, string> = {
  kellerbier: "#c79144",
  wheat: "#e6c35a",
  festbier: "#8b3a1a",
  special: "#5b6f8a",
};

const DAY_MS = 86_400_000;
const ZOOM_WIDTHS = [18, 36, 64];
const PAST_DAYS = 7;
const FUTURE_DAYS = 42;

interface Selected {
  sud: Sud;
  occ: Occupancy;
}

/** Touch-first planning timeline (Track C): tap a block to select it,
 * then move it with the day buttons or re-tank it via the dropdown —
 * no drag geometry, so it works with gloves in the cellar. */
export function Zeitplan({ tanks, sude, onMoveOccupancy }: ZeitplanProps) {
  const [zoom, setZoom] = useState(1);
  const [selected, setSelected] = useState<Selected | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const dayWidth = ZOOM_WIDTHS[zoom];

  const windowStart = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d.getTime() - PAST_DAYS * DAY_MS;
  }, []);
  const totalDays = PAST_DAYS + FUTURE_DAYS;

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

  // Land on "today" when the plan opens; the past is one swipe away.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollLeft = Math.max(0, (PAST_DAYS - 1) * dayWidth);
     
  }, [dayWidth]);

  const nowOffset = ((Date.now() - windowStart) / DAY_MS) * dayWidth;

  const moveSelected = (deltaDays: number) => {
    if (!selected) return;
    const nextStart =
      new Date(selected.occ.start_at).getTime() + deltaDays * DAY_MS;
    onMoveOccupancy(selected.sud.id, selected.occ.id, selected.occ.tank_id, nextStart);
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

  return (
    <div className="zeitplan">
      <div className="zeitplan-toolbar">
        <button
          type="button"
          aria-label="Verkleinern"
          disabled={zoom === 0}
          onClick={() => setZoom((z) => Math.max(0, z - 1))}
        >
          −
        </button>
        <button
          type="button"
          aria-label="Vergrößern"
          disabled={zoom === ZOOM_WIDTHS.length - 1}
          onClick={() => setZoom((z) => Math.min(ZOOM_WIDTHS.length - 1, z + 1))}
        >
          +
        </button>
        <button
          type="button"
          onClick={() => {
            const el = scrollRef.current;
            if (el) el.scrollLeft = Math.max(0, (PAST_DAYS - 1) * dayWidth);
          }}
        >
          Heute
        </button>
        <span className="muted">Sud antippen, dann unten verschieben.</span>
      </div>

      <div className="zeitplan-scroll" ref={scrollRef}>
        <div
          className="zeitplan-grid"
          style={{ width: totalDays * dayWidth + 140 }}
        >
          <div className="zeitplan-header">
            <div className="zeitplan-tanklabel" />
            <div className="zeitplan-days" style={{ width: totalDays * dayWidth }}>
              {days.map((d, i) => (
                <div
                  key={d.getTime()}
                  className={
                    d.getDay() === 0 || d.getDay() === 6
                      ? "zeitplan-day weekend"
                      : "zeitplan-day"
                  }
                  style={{ width: dayWidth, left: i * dayWidth }}
                >
                  {zoom > 0 || d.getDate() === 1 || d.getDay() === 1
                    ? `${d.getDate()}.${d.getMonth() + 1}.`
                    : ""}
                </div>
              ))}
            </div>
          </div>

          {rows.map((tank) => (
            <div className="zeitplan-row" key={tank.id}>
              <div className="zeitplan-tanklabel">
                <strong>{tank.name}</strong>
                <span className="muted">
                  {STAGE_LABEL[tank.stage]} · {tank.capacity_hl} hl
                </span>
              </div>
              <div
                className="zeitplan-track"
                style={{ width: totalDays * dayWidth }}
              >
                {nowOffset >= 0 && nowOffset <= totalDays * dayWidth && (
                  <div className="zeitplan-now" style={{ left: nowOffset }} />
                )}
                {(blocksByTank.get(tank.id) ?? []).map(({ sud, occ }) => {
                  const start = new Date(occ.start_at).getTime();
                  const end = occ.end_at
                    ? new Date(occ.end_at).getTime()
                    : windowStart + totalDays * DAY_MS;
                  const left = ((start - windowStart) / DAY_MS) * dayWidth;
                  const width = Math.max(
                    ((end - start) / DAY_MS) * dayWidth,
                    32,
                  );
                  if (left + width < 0 || left > totalDays * dayWidth) return null;
                  const isSelected =
                    selected?.occ.id === occ.id && selected.sud.id === sud.id;
                  const warned = (sud.warnings?.length ?? 0) > 0;
                  return (
                    <button
                      type="button"
                      key={occ.id}
                      className={
                        "zeitplan-block" +
                        (isSelected ? " selected" : "") +
                        (warned ? " warn" : "")
                      }
                      style={{
                        left: Math.max(left, 0),
                        width: left < 0 ? width + left : width,
                        background: warned
                          ? undefined
                          : STYLE_COLOR[sud.recipe.beer_style] ?? "#888",
                      }}
                      onClick={() =>
                        setSelected(isSelected ? null : { sud, occ })
                      }
                    >
                      {sudNumberLabel(sud, sude)}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {selected && (
        <div className="zeitplan-actionbar" role="toolbar" aria-label="Sud verschieben">
          <div className="zeitplan-actioninfo">
            <strong>
              {selected.sud.recipe.name} {sudNumberLabel(selected.sud, sude)}
            </strong>
            <span className="muted">
              {STAGE_LABEL[selected.occ.stage]} · ab{" "}
              {new Date(selected.occ.start_at).toLocaleDateString("de-DE")}
            </span>
          </div>
          <div className="zeitplan-actions">
            <button type="button" onClick={() => moveSelected(-7)}>
              −7
            </button>
            <button type="button" onClick={() => moveSelected(-1)}>
              −1 Tag
            </button>
            <button type="button" onClick={() => moveSelected(1)}>
              +1 Tag
            </button>
            <button type="button" onClick={() => moveSelected(7)}>
              +7
            </button>
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
