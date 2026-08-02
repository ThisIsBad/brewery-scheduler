import { useState } from "react";

import { api } from "../api/client";
import type { Occupancy, Sud, Tank } from "../api/types";
import { formatHl, remainingHl, sudNumberLabel } from "../domain";

interface WithdrawDialogProps {
  sud: Sud;
  occupancy: Occupancy;
  tanks: Tank[];
  sude: Sud[];
  onClose: () => void;
  onDone: (updated: Sud) => void;
}

export function WithdrawDialog({
  sud,
  occupancy,
  tanks,
  sude,
  onClose,
  onDone,
}: WithdrawDialogProps) {
  const remaining = remainingHl(sud, sude, occupancy);
  const tank = tanks.find((t) => t.id === occupancy.tank_id);
  const [volume, setVolume] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsed = parseFloat(volume) || 0;
  const canSubmit = parsed > 0 && parsed <= remaining;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await api.withdraw(sud.id, {
        tank_id: occupancy.tank_id,
        volume_hl: parsed,
        at: new Date().toISOString(),
        notes: notes || undefined,
      });
      onDone(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="dialog-backdrop" role="dialog" aria-label="Fass abfüllen">
      <form className="dialog" onSubmit={handleSubmit}>
        <h2>
          Fass abfüllen: {sud.recipe.name} {sudNumberLabel(sud, sude)}
        </h2>
        <p className="muted">
          Aus {tank?.name ?? "?"} · noch {formatHl(remaining)} im Tank
        </p>

        <label>
          Menge (hl)
          <input
            type="number"
            min="0.1"
            max={remaining}
            step="0.1"
            value={volume}
            onChange={(e) => setVolume(e.target.value)}
            required
          />
        </label>

        <label>
          Notiz (optional)
          <input
            type="text"
            value={notes}
            maxLength={200}
            placeholder="z. B. 4 Fässer Festzelt"
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>

        {parsed > remaining && (
          <div className="error">
            Nur {formatHl(remaining)} verfügbar.
          </div>
        )}
        {error && <div className="error">{error}</div>}

        <div className="dialog-actions">
          <button type="button" onClick={onClose} disabled={submitting}>
            Abbrechen
          </button>
          <button type="submit" disabled={!canSubmit || submitting}>
            {submitting ? "Speichere …" : "Abfüllen"}
          </button>
        </div>
      </form>
    </div>
  );
}
