import { useState } from "react";

import { api } from "../api/client";
import type { Location, Tank, TankStage } from "../api/types";
import { STAGE_LABEL, STAGE_ORDER, formatHl } from "../domain";

interface TankverwaltungProps {
  tanks: Tank[];
  locations: Location[];
  onReload: () => void;
}

type DialogState =
  | { kind: "create-tank" }
  | { kind: "edit-tank"; tank: Tank }
  | { kind: "create-location" }
  | { kind: "edit-location"; location: Location }
  | null;

export function Tankverwaltung({ tanks, locations, onReload }: TankverwaltungProps) {
  const [dialog, setDialog] = useState<DialogState>(null);
  const [reactivating, setReactivating] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const active = tanks.filter((t) => t.active);
  const inactive = tanks.filter((t) => !t.active);
  // Anzeigeordnung (Stefan, 2026-08-06): Typ (Gär < Lager < Ausschank,
  // beide Gärstufen zählen als Gärtank) → Größe aufsteigend → Name.
  const typRang = (t: Tank) =>
    t.stage === "storage" ? 1 : t.stage === "ausschank" ? 2 : 0;
  const byStage = (a: Tank, b: Tank) =>
    typRang(a) - typRang(b) ||
    a.capacity_hl - b.capacity_hl ||
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

      {locations.map((location) => {
        const group = active
          .filter((t) => t.location_id === location.id)
          .sort(byStage);
        return (
          <section key={location.id}>
            <h2>
              {location.name}
              <button
                type="button"
                className="location-edit"
                aria-label={`Standort ${location.name} bearbeiten`}
                onClick={() => setDialog({ kind: "edit-location", location })}
              >
                ✎
              </button>
            </h2>
            {group.length === 0 && <p className="muted">Keine Tanks.</p>}
            {group.map((t) => (
              <button
                type="button"
                className="tank-row"
                key={t.id}
                onClick={() => setDialog({ kind: "edit-tank", tank: t })}
              >
                <strong>{t.locked ? `🔒 ${t.name}` : t.name}</strong>
                <span className="muted">
                  {STAGE_LABEL[t.stage]} · {formatHl(t.capacity_hl)}
                </span>
              </button>
            ))}
          </section>
        );
      })}

      <section className="tank-actions">
        <button type="button" onClick={() => setDialog({ kind: "create-tank" })}>
          + Tank
        </button>
        <button
          type="button"
          className="secondary"
          onClick={() => setDialog({ kind: "create-location" })}
        >
          + Standort
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

      {(dialog?.kind === "create-tank" || dialog?.kind === "edit-tank") && (
        <TankDialog
          tank={dialog.kind === "edit-tank" ? dialog.tank : null}
          locations={locations}
          onClose={() => setDialog(null)}
          onDone={() => {
            setDialog(null);
            onReload();
          }}
        />
      )}
      {(dialog?.kind === "create-location" || dialog?.kind === "edit-location") && (
        <LocationDialog
          location={dialog.kind === "edit-location" ? dialog.location : null}
          hasTanks={
            dialog.kind === "edit-location"
              ? tanks.some((t) => t.location_id === dialog.location.id)
              : false
          }
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
  locations: Location[];
  onClose: () => void;
  onDone: () => void;
}

function TankDialog({ tank, locations, onClose, onDone }: TankDialogProps) {
  const [name, setName] = useState(tank?.name ?? "");
  const [locationId, setLocationId] = useState(
    tank?.location_id ?? locations[0]?.id ?? "",
  );
  const [stage, setStage] = useState<TankStage>(tank?.stage ?? "storage");
  const [capacity, setCapacity] = useState(
    tank ? String(tank.capacity_hl) : "",
  );
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isLocked = tank?.locked ?? false;
  const capacityHl = parseFloat(capacity);
  const canSubmit =
    !isLocked && name.trim() !== "" && capacityHl > 0 && locationId !== "";

  const toggleLock = async () => {
    if (!tank) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.updateTank(tank.id, { locked: !tank.locked });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      if (tank) {
        await api.updateTank(tank.id, {
          name: name.trim(),
          location_id: locationId,
          stage,
          capacity_hl: capacityHl,
        });
      } else {
        await api.createTank({
          name: name.trim(),
          location_id: locationId,
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
        {isLocked && (
          <p className="muted">
            🔒 Gesperrt — Stammdaten sind schreibgeschützt. Belegen bleibt
            möglich.
          </p>
        )}

        <label>
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={32}
            disabled={isLocked}
            required
          />
        </label>
        <label>
          Standort
          <select
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
            disabled={isLocked}
            required
          >
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Typ
          <select
            value={stage}
            onChange={(e) => setStage(e.target.value as TankStage)}
            disabled={isLocked}
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
            disabled={isLocked}
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

        {tank && (
          <button
            type="button"
            className="secondary lock-toggle"
            disabled={submitting}
            onClick={() => void toggleLock()}
          >
            {isLocked ? "🔓 Entsperren" : "🔒 Sperren"}
          </button>
        )}

        {tank && !isLocked && !confirmDelete && (
          <button
            type="button"
            className="danger"
            disabled={submitting}
            onClick={() => setConfirmDelete(true)}
          >
            Entfernen
          </button>
        )}
        {tank && !isLocked && confirmDelete && (
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

interface LocationDialogProps {
  /** null = create a new location */
  location: Location | null;
  hasTanks: boolean;
  onClose: () => void;
  onDone: () => void;
}

function LocationDialog({ location, hasTanks, onClose, onDone }: LocationDialogProps) {
  const [name, setName] = useState(location?.name ?? "");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = name.trim() !== "";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      if (location) {
        await api.updateLocation(location.id, { name: name.trim() });
      } else {
        await api.createLocation({ name: name.trim() });
      }
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!location) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.deleteLocation(location.id);
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
      aria-label={location ? "Standort bearbeiten" : "Standort anlegen"}
    >
      <form className="dialog" onSubmit={handleSubmit}>
        <h2>{location ? `Standort ${location.name}` : "Neuer Standort"}</h2>

        <label>
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={64}
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

        {location && !confirmDelete && (
          <button
            type="button"
            className="danger"
            disabled={submitting || hasTanks}
            title={hasTanks ? "Erst alle Tanks verschieben oder entfernen." : undefined}
            onClick={() => setConfirmDelete(true)}
          >
            {hasTanks ? "Entfernen (Tanks vorhanden)" : "Entfernen"}
          </button>
        )}
        {location && confirmDelete && (
          <div className="confirm-delete">
            <p className="muted">Standort wirklich entfernen?</p>
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
