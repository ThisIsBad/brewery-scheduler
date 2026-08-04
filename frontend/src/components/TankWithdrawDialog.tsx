import { useState } from "react";

import { api } from "../api/client";
import type { Occupancy, Sud, Tank, WithdrawalKind } from "../api/types";
import { formatHl, remainingHl, sudNumberLabel } from "../domain";

interface TankWithdrawDialogProps {
  tank: Tank;
  entries: { sud: Sud; occ: Occupancy }[];
  sude: Sud[];
  kind: WithdrawalKind;
  onClose: () => void;
  onDone: (updated: Sud[]) => void;
}

const KEG_SIZES = [10, 20, 30, 50];

const KIND_TITLE: Record<WithdrawalKind, string> = {
  keg_fill: "Fass abfüllen",
  ausschank: "Ausschank eintragen",
  schwund: "Schwund ausbuchen",
};

const KIND_SUBMIT: Record<WithdrawalKind, string> = {
  keg_fill: "Abfüllen",
  ausschank: "Eintragen",
  schwund: "Ausbuchen",
};

/** Blending (2026-08-04): the booking happens on the TANK; the server
 * distributes it proportionally across the contained Sud shares. */
export function TankWithdrawDialog({
  tank,
  entries,
  sude,
  kind,
  onClose,
  onDone,
}: TankWithdrawDialogProps) {
  const withRemaining = entries.map((e) => ({
    ...e,
    remaining: remainingHl(e.sud, sude, e.occ),
  }));
  const total = withRemaining.reduce((sum, e) => sum + e.remaining, 0);

  const [volume, setVolume] = useState("");
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
  const canSubmit = parsed > 0 && parsed <= total + 1e-9;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await api.tankWithdraw(tank.id, {
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
          {KIND_TITLE[kind]}: {tank.name}
        </h2>
        <p className="muted">
          {withRemaining
            .map(
              (e) =>
                `${e.sud.recipe.name} ${sudNumberLabel(e.sud, sude)} ${formatHl(
                  e.remaining,
                )}`,
            )
            .join(" · ")}{" "}
          — zusammen {formatHl(total)}
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
            <p className={parsed > total + 1e-9 ? "error" : "muted"}>
              Ergibt {formatHl(parsed)}
            </p>
          </>
        ) : (
          <label>
            Menge (hl)
            <input
              type="number"
              min="0.1"
              max={total}
              step="0.1"
              value={volume}
              onChange={(e) => setVolume(e.target.value)}
              required
            />
          </label>
        )}

        {entries.length > 1 && parsed > 0 && parsed <= total + 1e-9 && (
          <p className="muted">
            Verteilt sich:{" "}
            {withRemaining
              .map(
                (e) =>
                  `${e.sud.recipe.name} ~${formatHl(
                    Math.round((parsed * e.remaining * 10) / total) / 10,
                  )}`,
              )
              .join(" · ")}
          </p>
        )}

        <label>
          Notiz (optional)
          <input
            type="text"
            value={notes}
            maxLength={200}
            placeholder={
              kind === "schwund" ? "z. B. Geläger" : "z. B. Bergkirchweih"
            }
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>

        {parsed > total + 1e-9 && (
          <div className="error">Nur {formatHl(total)} im Tank.</div>
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
