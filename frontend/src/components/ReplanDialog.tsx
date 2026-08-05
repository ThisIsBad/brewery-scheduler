import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { Occupancy, ScheduleOccupancyIn, Sud, Tank } from "../api/types";
import {
  STAGE_LABEL,
  batchRemainingHl,
  formatHl,
  sudNumberLabel,
} from "../domain";

interface ReplanDialogProps {
  sud: Sud;
  firstOccupancy: Occupancy;
  tanks: Tank[];
  sude: Sud[];
  onClose: () => void;
  onDone: (updated: Sud) => void;
}

function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Move a planned Sud: pick a new start and/or tank for its first upcoming
 * occupancy; all later occupancies shift by the same delta so the plan's
 * shape (fermentation → storage windows) stays intact. */
export function ReplanDialog({
  sud,
  firstOccupancy,
  tanks,
  sude,
  onClose,
  onDone,
}: ReplanDialogProps) {
  const remaining = batchRemainingHl(sud, sude);
  const candidates = useMemo(
    () =>
      tanks.filter(
        (t) =>
          t.stage === firstOccupancy.stage &&
          t.active &&
          t.capacity_hl >= remaining,
      ),
    [tanks, firstOccupancy.stage, remaining],
  );

  const [tankId, setTankId] = useState(firstOccupancy.tank_id);
  const [startAt, setStartAt] = useState(
    toLocalInputValue(new Date(firstOccupancy.start_at)),
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const newStart = new Date(startAt);
    const delta =
      newStart.getTime() - new Date(firstOccupancy.start_at).getTime();

    const shift = (iso: string) => new Date(new Date(iso).getTime() + delta);
    const payload: ScheduleOccupancyIn[] = sud.occupancies.map((o) => ({
      tank_id: o.id === firstOccupancy.id ? tankId : o.tank_id,
      stage: o.stage,
      start_at: shift(o.start_at).toISOString(),
      end_at: o.end_at ? shift(o.end_at).toISOString() : null,
      volume_hl: o.volume_hl,
    }));

    try {
      const updated = await api.updateSchedule(sud.id, { occupancies: payload });
      onDone(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="dialog-backdrop" role="dialog" aria-label="Umplanen">
      <form className="dialog" onSubmit={handleSubmit}>
        <h2>
          Umplanen: {sudNumberLabel(sud, sude)} · {sud.recipe.name}
        </h2>
        <p className="muted">
          {formatHl(remaining)} · Folgeschritte verschieben sich mit
        </p>

        <label>
          {STAGE_LABEL[firstOccupancy.stage]}
          <select
            value={tankId}
            onChange={(e) => setTankId(e.target.value)}
            required
          >
            {candidates.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name} ({formatHl(t.capacity_hl)})
              </option>
            ))}
          </select>
        </label>

        <label>
          Start
          <input
            type="datetime-local"
            value={startAt}
            onChange={(e) => setStartAt(e.target.value)}
            required
          />
        </label>

        {error && <div className="error">{error}</div>}

        <div className="dialog-actions">
          <button type="button" onClick={onClose} disabled={submitting}>
            Abbrechen
          </button>
          <button type="submit" disabled={submitting}>
            {submitting ? "Speichere …" : "Umplanen"}
          </button>
        </div>
      </form>
    </div>
  );
}
