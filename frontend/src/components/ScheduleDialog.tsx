import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { Sud, Tank, TankStage } from "../api/types";
import { combinedVolumeHl, formatHl, sudNumberLabel } from "../domain";

interface ScheduleDialogProps {
  sud: Sud;
  tanks: Tank[];
  sude: Sud[];
  onClose: () => void;
  onDone: (updated: Sud) => void;
}

function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
}

export function ScheduleDialog({
  sud,
  tanks,
  sude,
  onClose,
  onDone,
}: ScheduleDialogProps) {
  // Wheat starts in the open fermenter, everything else in a closed one —
  // same recipe-driven rule the create dialog applies; the server enforces
  // it regardless.
  const stage: TankStage = sud.recipe.open_fermentation_required
    ? "fermentation_open"
    : "fermentation_closed";
  // Per-Sud overrides win over the recipe — the same effective view the
  // backend applies to derived end dates and warnings.
  const overrides = sud.recipe_overrides ?? {};
  const hasOverride = sud.recipe.open_fermentation_required
    ? overrides.open_fermentation_duration_days != null
    : overrides.fermentation_duration_days != null;
  const durationDays = sud.recipe.open_fermentation_required
    ? (overrides.open_fermentation_duration_days ??
      sud.recipe.open_fermentation_duration_days ??
      4)
    : (overrides.fermentation_duration_days ??
      sud.recipe.fermentation_duration_days);

  // Merged batches share the lead's tank — offer only fermenters that fit
  // the combined volume, matching the server's capacity rule.
  const combined = combinedVolumeHl(sud, sude);
  const candidates = useMemo(
    () =>
      tanks.filter(
        (t) => t.stage === stage && t.active && t.capacity_hl >= combined,
      ),
    [tanks, stage, combined],
  );

  const [tankId, setTankId] = useState("");
  // Fermentation starts Brauzeit + 8 h by default (the brewhouse day);
  // for Sude brewed in the past the default falls back to now.
  const defaultStart = (() => {
    const fromBrew = new Date(new Date(sud.brew_at).getTime() + 8 * 3_600_000);
    return fromBrew > new Date() ? fromBrew : new Date();
  })();
  const [startAt, setStartAt] = useState(toLocalInputValue(defaultStart));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!tankId) return;
    setSubmitting(true);
    setError(null);
    const start = new Date(startAt);
    const end = new Date(start.getTime() + durationDays * 86_400_000);
    try {
      const updated = await api.updateSchedule(sud.id, {
        occupancies: [
          {
            tank_id: tankId,
            stage,
            start_at: start.toISOString(),
            end_at: end.toISOString(),
          },
        ],
      });
      onDone(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="dialog-backdrop" role="dialog" aria-label="Einplanen">
      <form className="dialog" onSubmit={handleSubmit}>
        <h2>
          Einplanen: {sudNumberLabel(sud, sude)} · {sud.recipe.name}
        </h2>
        <p className="muted">{formatHl(combined)} in den Gärtank</p>

        <label>
          {stage === "fermentation_open" ? "Gärtank (offen)" : "Gärtank"}
          <select
            value={tankId}
            onChange={(e) => setTankId(e.target.value)}
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

        <label>
          Start
          <input
            type="datetime-local"
            value={startAt}
            onChange={(e) => setStartAt(e.target.value)}
            required
          />
        </label>

        <p className="muted">
          Gärdauer {hasOverride ? "laut Abweichung" : "laut Rezept"}:{" "}
          {durationDays} Tage — Ende wird automatisch gesetzt.
        </p>

        {error && <div className="error">{error}</div>}

        <div className="dialog-actions">
          <button type="button" onClick={onClose} disabled={submitting}>
            Abbrechen
          </button>
          <button type="submit" disabled={!tankId || submitting}>
            {submitting ? "Speichere …" : "Einplanen"}
          </button>
        </div>
      </form>
    </div>
  );
}
