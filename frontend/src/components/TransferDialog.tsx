import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { Occupancy, Sud, Tank, TransferAllocationIn } from "../api/types";
import {
  STAGE_LABEL,
  STAGE_ORDER,
  batchRemainingHl,
  formatHl,
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
  // What moves is what physically remains — kegs and pours already taken
  // out stay out (mirrors the transfer endpoint's remaining-volume rule).
  const combined = batchRemainingHl(sud, sude);

  // Any active tank except the one the beer sits in — the usual
  // Gärtank → Lagertank → Ausschank order is convention, not a constraint.
  // Outside the Ausschank stage a tank must fit the whole batch and be free
  // right now; Ausschank tanks blend batches, so all are offered and the
  // headroom rule decides server-side.
  const now = useMemo(() => new Date(), []);
  const candidates = useMemo(() => {
    return tanks.filter((t) => {
      if (!t.active || t.id === occupancy.tank_id) return false;
      if (t.stage === "ausschank") return true;
      if (t.capacity_hl < combined) return false;
      const occupiedNow = sude.some((s) =>
        s.occupancies.some(
          (o) => o.tank_id === t.id && occupancyAt(s, now)?.id === o.id,
        ),
      );
      return !occupiedNow;
    });
  }, [tanks, sude, combined, now, occupancy.tank_id]);
  const ausschankTanks = candidates.filter((t) => t.stage === "ausschank");

  const [targetId, setTargetId] = useState<string>("");
  const [allocations, setAllocations] = useState<
    { tank_id: string; volume: string }[]
  >([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const targetTank = tanks.find((t) => t.id === targetId) ?? null;
  const isAusschank = targetTank?.stage === "ausschank";

  const selectTarget = (id: string) => {
    setTargetId(id);
    const tank = tanks.find((t) => t.id === id);
    // An Ausschank target can split across several tanks; start with the
    // whole batch in the chosen one so the common case needs no typing.
    setAllocations(
      tank?.stage === "ausschank"
        ? [{ tank_id: id, volume: String(combined) }]
        : [],
    );
  };

  const allocationSum = allocations.reduce(
    (sum, a) => sum + (parseFloat(a.volume) || 0),
    0,
  );
  const canSubmit = isAusschank
    ? allocations.every((a) => a.tank_id && parseFloat(a.volume) > 0) &&
      Math.abs(allocationSum - combined) < 0.01
    : targetId !== "";

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
      : [{ tank_id: targetId }];
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
          {formatHl(combined)}
          {targetTank
            ? ` → ${targetTank.name} (${STAGE_LABEL[targetTank.stage]})`
            : " — Ziel wählen"}
        </p>

        <label>
          Zieltank
          <select
            value={targetId}
            onChange={(e) => selectTarget(e.target.value)}
            required
          >
            <option value="">— wählen —</option>
            {STAGE_ORDER.map((stage) => {
              const group = candidates.filter((t) => t.stage === stage);
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
            })}
          </select>
        </label>

        {isAusschank && (
          <>
            {allocations.map((a, i) => (
              <div className="allocation-row" key={i}>
                <select
                  aria-label={`Ausschanktank ${i + 1}`}
                  value={a.tank_id}
                  onChange={(e) => {
                    const value = e.target.value;
                    setAllocations((prev) =>
                      prev.map((x, j) =>
                        j === i ? { ...x, tank_id: value } : x,
                      ),
                    );
                    if (i === 0) setTargetId(value);
                  }}
                  required
                >
                  <option value="">— Tank —</option>
                  {ausschankTanks
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
            {ausschankTanks.length > allocations.length && (
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
