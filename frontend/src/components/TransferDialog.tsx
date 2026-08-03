import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { Occupancy, Sud, Tank, TransferAllocationIn } from "../api/types";
import {
  STAGE_LABEL,
  batchRemainingHl,
  formatHl,
  nextStage,
  occupancyAt,
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
  const target = nextStage(occupancy.stage);
  // What moves is what physically remains — kegs and pours already taken
  // out stay out (mirrors the transfer endpoint's remaining-volume rule).
  const combined = batchRemainingHl(sud, sude);
  const isAusschank = target === "ausschank";

  // Candidate tanks for the target stage. Pre-Ausschank the batch stays
  // together, so only tanks that fit the whole batch and are free right now
  // are offered — the server re-validates everything anyway. Ausschank tanks
  // blend batches, so all active ones are offered and the headroom rule
  // decides server-side.
  const now = useMemo(() => new Date(), []);
  const candidates = useMemo(() => {
    if (!target) return [];
    return tanks.filter((t) => {
      if (t.stage !== target || !t.active) return false;
      if (isAusschank) return true;
      if (t.capacity_hl < combined) return false;
      const occupiedNow = sude.some((s) =>
        s.occupancies.some(
          (o) =>
            o.tank_id === t.id &&
            occupancyAt(s, now)?.id === o.id,
        ),
      );
      return !occupiedNow;
    });
  }, [tanks, sude, target, isAusschank, combined, now]);

  const [singleTank, setSingleTank] = useState<string>("");
  const [allocations, setAllocations] = useState<
    { tank_id: string; volume: string }[]
  >([{ tank_id: "", volume: String(combined) }]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!target) return null;

  const allocationSum = allocations.reduce(
    (sum, a) => sum + (parseFloat(a.volume) || 0),
    0,
  );
  const canSubmit = isAusschank
    ? allocations.every((a) => a.tank_id && parseFloat(a.volume) > 0) &&
      Math.abs(allocationSum - combined) < 0.01
    : singleTank !== "";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    const payload_allocations: TransferAllocationIn[] = isAusschank
      ? allocations.map((a) => ({
          tank_id: a.tank_id,
          volume_hl: parseFloat(a.volume),
        }))
      : [{ tank_id: singleTank }];
    try {
      const updated = await api.transferSud(sud.id, {
        start_at: new Date().toISOString(),
        end_at: null,
        allocations: payload_allocations,
      });
      onDone(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="dialog-backdrop" role="dialog" aria-label="Umdrücken">
      <form className="dialog" onSubmit={handleSubmit}>
        <h2>
          Umdrücken: {sud.recipe.name} {sudNumberLabel(sud, sude)}
        </h2>
        <p className="muted">
          {formatHl(combined)} → {STAGE_LABEL[target]}
        </p>

        {!isAusschank && (
          <label>
            Zieltank
            <select
              value={singleTank}
              onChange={(e) => setSingleTank(e.target.value)}
              required
            >
              <option value="">— wählen —</option>
              {candidates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({formatHl(t.capacity_hl)})
                </option>
              ))}
            </select>
          </label>
        )}

        {isAusschank && (
          <>
            {allocations.map((a, i) => (
              <div className="allocation-row" key={i}>
                <select
                  aria-label={`Ausschanktank ${i + 1}`}
                  value={a.tank_id}
                  onChange={(e) =>
                    setAllocations((prev) =>
                      prev.map((x, j) =>
                        j === i ? { ...x, tank_id: e.target.value } : x,
                      ),
                    )
                  }
                  required
                >
                  <option value="">— Tank —</option>
                  {candidates
                    .filter(
                      (t) =>
                        t.id === a.tank_id ||
                        !allocations.some((other) => other.tank_id === t.id),
                    )
                    .map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name} ({formatHl(t.capacity_hl)})
                      </option>
                    ))}
                </select>
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
                {allocations.length > 1 && (
                  <button
                    type="button"
                    className="secondary"
                    onClick={() =>
                      setAllocations((prev) => prev.filter((_, j) => j !== i))
                    }
                  >
                    ✕
                  </button>
                )}
              </div>
            ))}
            <button
              type="button"
              className="secondary"
              onClick={() =>
                setAllocations((prev) => [...prev, { tank_id: "", volume: "" }])
              }
            >
              + Tank aufteilen
            </button>
            <p className={Math.abs(allocationSum - combined) < 0.01 ? "muted" : "error"}>
              Aufgeteilt: {formatHl(allocationSum)} von {formatHl(combined)}
            </p>
          </>
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
