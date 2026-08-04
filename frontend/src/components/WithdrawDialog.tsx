import { useState } from "react";

import { api } from "../api/client";
import type { Occupancy, Sud, Tank, WithdrawalKind } from "../api/types";
import { formatHl, remainingHl, sudNumberLabel } from "../domain";

interface WithdrawDialogProps {
  sud: Sud;
  occupancy: Occupancy;
  tanks: Tank[];
  sude: Sud[];
  kind: WithdrawalKind;
  onClose: () => void;
  onDone: (updated: Sud) => void;
}

const KEG_SIZES = [10, 20, 30, 50];

const KIND_TITLE: Record<WithdrawalKind, string> = {
  keg_fill: "Fass abfüllen",
  ausschank: "Ausschank eintragen",
};

const KIND_SUBMIT: Record<WithdrawalKind, string> = {
  keg_fill: "Abfüllen",
  ausschank: "Eintragen",
};

export function WithdrawDialog({
  sud,
  occupancy,
  tanks,
  sude,
  kind,
  onClose,
  onDone,
}: WithdrawDialogProps) {
  const remaining = remainingHl(sud, sude, occupancy);
  const tank = tanks.find((t) => t.id === occupancy.tank_id);
  const [volume, setVolume] = useState("");
  // Keg fills are entered as counts per barrel size (2026-08-04); the hl
  // volume is computed. Pours keep the direct hl field.
  const [counts, setCounts] = useState<Record<number, string>>({});
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isKegFill = kind === "keg_fill";
  const kegs = KEG_SIZES.map((size) => ({
    size_l: size,
    count: parseInt(counts[size] || "0", 10) || 0,
  })).filter((k) => k.count > 0);
  const kegVolume = kegs.reduce((sum, k) => sum + (k.size_l * k.count) / 100, 0);
  const parsed = isKegFill ? kegVolume : parseFloat(volume) || 0;
  const canSubmit = parsed > 0 && parsed <= remaining + 1e-9;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await api.withdraw(sud.id, {
        tank_id: occupancy.tank_id,
        ...(isKegFill ? { kegs } : { volume_hl: parsed }),
        at: new Date().toISOString(),
        kind,
        notes: notes || undefined,
      });
      onDone(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <div className="dialog-backdrop" role="dialog" aria-label={KIND_TITLE[kind]}>
      <form className="dialog" onSubmit={handleSubmit}>
        <h2>
          {KIND_TITLE[kind]}: {sud.recipe.name} {sudNumberLabel(sud, sude)}
        </h2>
        <p className="muted">
          Aus {tank?.name ?? "?"} · noch {formatHl(remaining)} im Tank
        </p>

        {isKegFill ? (
          <>
            {KEG_SIZES.map((size) => (
              <label key={size}>
                Fässer {size} l (Stück)
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={counts[size] ?? ""}
                  onChange={(e) =>
                    setCounts((prev) => ({ ...prev, [size]: e.target.value }))
                  }
                />
              </label>
            ))}
            <p className={parsed > remaining + 1e-9 ? "error" : "muted"}>
              Ergibt {formatHl(parsed)}
            </p>
          </>
        ) : (
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
        )}

        <label>
          Notiz (optional)
          <input
            type="text"
            value={notes}
            maxLength={200}
            placeholder={
              kind === "keg_fill" ? "z. B. 4 Fässer Festzelt" : "z. B. Bergkirchweih"
            }
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
            {submitting ? "Speichere …" : KIND_SUBMIT[kind]}
          </button>
        </div>
      </form>
    </div>
  );
}
