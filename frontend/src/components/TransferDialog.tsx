import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { Occupancy, Sud, Tank, TransferAllocationIn } from "../api/types";
import {
  STAGE_LABEL,
  STAGE_ORDER,
  formatHl,
  remainingHl,
  sudNumberLabel,
} from "../domain";

interface TransferDialogProps {
  sud: Sud;
  occupancy: Occupancy;
  tanks: Tank[];
  sude: Sud[];
  onClose: () => void;
  onDone: (updated: Sud) => void;
}

export function TransferDialog({
  sud,
  occupancy,
  tanks,
  sude,
  onClose,
  onDone,
}: TransferDialogProps) {
  // What moves is what physically remains in the tapped tank — the whole
  // batch, or just this tank's share when it was split. Kegs and pours
  // already taken out stay out (mirrors the transfer endpoint).
  const combined = remainingHl(sud, sude, occupancy);
  const sourceTank = tanks.find((t) => t.id === occupancy.tank_id);

  // Any active tank except the one the beer sits in — the usual
  // Gärtank → Lagertank → Ausschank order is convention, not a constraint.
  // Outside the Ausschank stage a tank must be free right now; small tanks
  // stay in the list because the batch may split across several of them
  // (Stefan, 2026-08-04). Ausschank tanks blend batches of the SAME beer —
  // Sorten werden nie gemischt (Stefan, 2026-08-05) — so only empty or
  // same-style ones are offered; the headroom rule decides server-side.
  const now = useMemo(() => new Date(), []);
  const candidates = useMemo(() => {
    // Occupancy checks run per row, not via occupancyAt: a split batch
    // occupies several tanks at once and occupancyAt only ever returns
    // the first of them. For Ausschank tanks planned FUTURE occupancies
    // count too — the booking window starts now and stays open, so a
    // foreign style planned for next week would already collide.
    const activeNow = (o: Occupancy) =>
      new Date(o.start_at) <= now &&
      (o.end_at === null || new Date(o.end_at) > now);
    const openFromNow = (o: Occupancy) =>
      o.end_at === null || new Date(o.end_at) > now;
    return tanks.filter((t) => {
      if (!t.active || t.id === occupancy.tank_id) return false;
      if (t.stage === "ausschank") {
        const occupants = sude.filter((s) =>
          s.occupancies.some((o) => o.tank_id === t.id && openFromNow(o)),
        );
        return occupants.every(
          (s) => s.recipe.beer_style === sud.recipe.beer_style,
        );
      }
      const occupiedNow = sude.some((s) =>
        s.occupancies.some((o) => o.tank_id === t.id && activeNow(o)),
      );
      return !occupiedNow;
    });
  }, [tanks, sude, now, occupancy.tank_id, sud.recipe.beer_style]);

  // The split rows ARE the interface (Stefan, 2026-08-05): one row is a
  // plain move, „+ Tank aufteilen“ adds more. No separate target picker —
  // it only duplicated the first row.
  const [allocations, setAllocations] = useState<
    { tank_id: string; volume: string }[]
  >([{ tank_id: "", volume: "" }]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const targetTank = tanks.find((t) => t.id === allocations[0]?.tank_id) ?? null;
  const isAusschank = targetTank?.stage === "ausschank";
  const split = allocations.length > 1;
  // All targets of one Umdrücken share a stage (backend rule) — the later
  // rows only offer tanks matching the first pick.
  const sameStageTanks = candidates.filter(
    (t) => t.stage === targetTank?.stage,
  );

  const changeTank = (index: number, id: string) => {
    const tank = tanks.find((t) => t.id === id);
    setAllocations((prev) => {
      // Clearing or re-staging the first row invalidates the split — back
      // to a single row; the first row defines the stage for the rest.
      if (index === 0 && id === "") {
        return [{ tank_id: "", volume: "" }];
      }
      if (index === 0 && tank && tank.stage !== targetTank?.stage) {
        return [{ tank_id: id, volume: String(combined) }];
      }
      return prev.map((x, j) =>
        j === index
          ? {
              ...x,
              tank_id: id,
              volume: prev.length === 1 ? String(combined) : x.volume,
            }
          : x,
      );
    });
  };

  const allocationSum = allocations.reduce(
    (sum, a) => sum + (parseFloat(a.volume) || 0),
    0,
  );
  // Outside Ausschank each share must fit its tank outright; Ausschank
  // headroom (blending) is decided server-side.
  const overfilled = allocations
    .map((a) => {
      const tank = tanks.find((t) => t.id === a.tank_id);
      return tank &&
        tank.stage !== "ausschank" &&
        (parseFloat(a.volume) || 0) > tank.capacity_hl
        ? tank
        : null;
    })
    .filter((t): t is Tank => t !== null);
  const canSubmit =
    allocations.every((a) => a.tank_id && parseFloat(a.volume) > 0) &&
    Math.abs(allocationSum - combined) < 0.01 &&
    overfilled.length === 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    // A lone non-Ausschank target moves the whole batch — no explicit
    // volume, matching the backend's full-batch convention. Splits and
    // Ausschank targets always carry their shares.
    const payload_allocations: TransferAllocationIn[] =
      !isAusschank && !split
        ? [{ tank_id: allocations[0].tank_id }]
        : allocations.map((a) => ({
            tank_id: a.tank_id,
            volume_hl: parseFloat(a.volume),
          }));
    try {
      const updated = await api.transferSud(sud.id, {
        start_at: new Date().toISOString(),
        end_at: null,
        from_tank_id: occupancy.tank_id,
        allocations: payload_allocations,
      });
      onDone(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  const optionsFor = (index: number) => {
    const pool = index === 0 ? candidates : sameStageTanks;
    return pool.filter(
      (t) =>
        t.id === allocations[index].tank_id ||
        !allocations.some((other) => other.tank_id === t.id),
    );
  };

  return (
    <div className="dialog-backdrop" role="dialog" aria-label="Umdrücken">
      <form className="dialog" onSubmit={handleSubmit}>
        <h2>
          Umdrücken: {sud.recipe.name} {sudNumberLabel(sud, sude)}
        </h2>
        <p className="muted">
          {formatHl(combined)} aus {sourceTank?.name ?? "?"}
          {targetTank
            ? ` → ${targetTank.name} (${STAGE_LABEL[targetTank.stage]})${
                split ? " + weitere" : ""
              }`
            : " — Ziel wählen"}
        </p>

        {allocations.map((a, i) => (
          <div className="allocation-row" key={i}>
            <select
              aria-label={i === 0 ? (split ? "Zieltank 1" : "Zieltank") : `Zieltank ${i + 1}`}
              value={a.tank_id}
              onChange={(e) => changeTank(i, e.target.value)}
              required
            >
              <option value="">— wählen —</option>
              {i === 0
                ? STAGE_ORDER.map((stage) => {
                    const group = optionsFor(i).filter(
                      (t) => t.stage === stage,
                    );
                    if (group.length === 0) return null;
                    return (
                      <optgroup key={stage} label={STAGE_LABEL[stage]}>
                        {group.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.name} ({formatHl(t.capacity_hl)})
                          </option>
                        ))}
                      </optgroup>
                    );
                  })
                : optionsFor(i).map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({formatHl(t.capacity_hl)})
                    </option>
                  ))}
            </select>
            {split && (
              <input
                aria-label={`Volumen ${i + 1} (hl)`}
                type="number"
                min="0.1"
                step="0.1"
                value={a.volume}
                onChange={(e) =>
                  setAllocations((prev) =>
                    prev.map((x, j) =>
                      j === i ? { ...x, volume: e.target.value } : x,
                    ),
                  )
                }
                required
              />
            )}
            {split && (
              <button
                type="button"
                className="secondary"
                aria-label={`Zeile ${i + 1} entfernen`}
                onClick={() =>
                  setAllocations((prev) =>
                    prev.length === 2
                      ? // Back to a plain single-tank move: the whole
                        // volume again goes into the remaining tank.
                        prev
                          .filter((_, j) => j !== i)
                          .map((x) => ({ ...x, volume: String(combined) }))
                      : prev.filter((_, j) => j !== i),
                  )
                }
              >
                ✕
              </button>
            )}
          </div>
        ))}

        {targetTank && sameStageTanks.length > allocations.length && (
          <button
            type="button"
            className="secondary"
            onClick={() =>
              setAllocations((prev) => [...prev, { tank_id: "", volume: "" }])
            }
          >
            + Tank aufteilen
          </button>
        )}
        {targetTank && (
          <p
            className={
              Math.abs(allocationSum - combined) < 0.01 ? "muted" : "error"
            }
          >
            Aufgeteilt: {formatHl(allocationSum)} von {formatHl(combined)}
          </p>
        )}
        {overfilled.length > 0 && (
          <div className="error">
            {overfilled[0].name} fasst nur{" "}
            {formatHl(overfilled[0].capacity_hl)} — Menge reduzieren oder
            weiter aufteilen.
          </div>
        )}

        {error && <div className="error">{error}</div>}

        <div className="dialog-actions">
          <button type="button" onClick={onClose} disabled={submitting}>
            Abbrechen
          </button>
          <button type="submit" disabled={!canSubmit || submitting}>
            {submitting ? "Speichere …" : "Umdrücken"}
          </button>
        </div>
      </form>
    </div>
  );
}
