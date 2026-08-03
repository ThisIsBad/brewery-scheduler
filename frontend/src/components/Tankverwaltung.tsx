import { useState } from "react";

import { api } from "../api/client";
import type { Tank, TankCellar, TankStage } from "../api/types";
import { CELLAR_LABEL, STAGE_LABEL, STAGE_ORDER, formatHl } from "../domain";

interface TankverwaltungProps {
  tanks: Tank[];
  onReload: () => void;
}

type DialogState = { kind: "create" } | { kind: "edit"; tank: Tank } | null;

const CELLARS: TankCellar[] = ["main", "secondary"];

export function Tankverwaltung({ tanks, onReload }: TankverwaltungProps) {
  const [dialog, setDialog] = useState<DialogState>(null);
  const [reactivating, setReactivating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const active = tanks.filter((t) => t.active);
  const inactive = tanks.filter((t) => !t.active);
  const byStage = (a: Tank, b: Tank) =>
    STAGE_ORDER.indexOf(a.stage) - STAGE_ORDER.indexOf(b.stage) ||
    a.name.localeCompare(b.name);

  const reactivate = async (tank: Tank) => {
    setReactivating(tank.id);
    setError(null);
    try {
      await api.updateTank(tank.id, { active: true });
      onReload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setReactivating(null);
    }
  };

  return (
    <div className="tankverwaltung">
      {error && <div className="error banner">{error}</div>}

      {CELLARS.map((cellar) => {
        const group = active.filter((t) => t.cellar === cellar).sort(byStage);
        if (group.length === 0) return null;
        return (
          <section key={cellar}>
            <h2>{CELLAR_LABEL[cellar]}</h2>
            {group.map((t) => (
              <button
                type="button"
                className="tank-row"
                key={t.id}
                onClick={() => setDialog({ kind: "edit", tank: t })}
              >
                <strong>{t.name}</strong>
                <span className="muted">
                  {STAGE_LABEL[t.stage]} · {formatHl(t.capacity_hl)}
                </span>
              </button>
            ))}
          </section>
        );
      })}

      <section>
        <button type="button" onClick={() => setDialog({ kind: "create" })}>
          + Tank
        </button>
      </section>

      {inactive.length > 0 && (
        <section>
          <h2>Ausgeblendet</h2>
          <p className="muted">
            Entfernte Tanks mit Historie — im Kellerbuch weiter sichtbar.
          </p>
          {inactive.map((t) => (
            <div className="tank-row" key={t.id}>
              <strong>{t.name}</strong>
              <span className="muted">
                {STAGE_LABEL[t.stage]} · {formatHl(t.capacity_hl)}
              </span>
              <button
                type="button"
                className="secondary"
                disabled={reactivating === t.id}
                onClick={() => void reactivate(t)}
              >
                Wieder aktivieren
              </button>
            </div>
          ))}
        </section>
      )}

      {dialog && (
        <TankDialog
          tank={dialog.kind === "edit" ? dialog.tank : null}
          onClose={() => setDialog(null)}
          onDone={() => {
            setDialog(null);
            onReload();
          }}
        />
      )}
    </div>
  );
}

interface TankDialogProps {
  /** null = create a new tank */
  tank: Tank | null;
  onClose: () => void;
  onDone: () => void;
}

function TankDialog({ tank, onClose, onDone }: TankDialogProps) {
  const [name, setName] = useState(tank?.name ?? "");
  const [cellar, setCellar] = useState<TankCellar>(tank?.cellar ?? "main");
  const [stage, setStage] = useState<TankStage>(tank?.stage ?? "storage");
  const [capacity, setCapacity] = useState(
    tank ? String(tank.capacity_hl) : "",
  );
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const capacityHl = parseFloat(capacity);
  const canSubmit = name.trim() !== "" && capacityHl > 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      if (tank) {
        await api.updateTank(tank.id, {
          name: name.trim(),
          cellar,
          stage,
          capacity_hl: capacityHl,
        });
      } else {
        await api.createTank({
          name: name.trim(),
          cellar,
          stage,
          capacity_hl: capacityHl,
        });
      }
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!tank) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.deleteTank(tank.id);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
      setConfirmDelete(false);
    }
  };

  return (
    <div
      className="dialog-backdrop"
      role="dialog"
      aria-label={tank ? "Tank bearbeiten" : "Tank anlegen"}
    >
      <form className="dialog" onSubmit={handleSubmit}>
        <h2>{tank ? `Tank ${tank.name}` : "Neuer Tank"}</h2>

        <label>
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={32}
            required
          />
        </label>
        <label>
          Keller
          <select
            value={cellar}
            onChange={(e) => setCellar(e.target.value as TankCellar)}
          >
            {CELLARS.map((c) => (
              <option key={c} value={c}>
                {CELLAR_LABEL[c]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Typ
          <select
            value={stage}
            onChange={(e) => setStage(e.target.value as TankStage)}
          >
            {STAGE_ORDER.map((s) => (
              <option key={s} value={s}>
                {STAGE_LABEL[s]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Kapazität (hl)
          <input
            type="number"
            min="0.5"
            step="0.5"
            value={capacity}
            onChange={(e) => setCapacity(e.target.value)}
            required
          />
        </label>

        {error && <div className="error">{error}</div>}

        <div className="dialog-actions">
          <button type="button" onClick={onClose} disabled={submitting}>
            Abbrechen
          </button>
          <button type="submit" disabled={!canSubmit || submitting}>
            {submitting ? "Speichere …" : "Speichern"}
          </button>
        </div>

        {tank && !confirmDelete && (
          <button
            type="button"
            className="danger"
            disabled={submitting}
            onClick={() => setConfirmDelete(true)}
          >
            Entfernen
          </button>
        )}
        {tank && confirmDelete && (
          <div className="confirm-delete">
            <p className="muted">
              Wirklich entfernen? Vergangene Belegungen bleiben im Kellerbuch
              erhalten.
            </p>
            <button
              type="button"
              className="danger"
              disabled={submitting}
              onClick={() => void handleDelete()}
            >
              Ja, entfernen
            </button>
          </div>
        )}
      </form>
    </div>
  );
}
