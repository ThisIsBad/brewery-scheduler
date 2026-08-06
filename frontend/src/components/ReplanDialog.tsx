import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { ScheduleOccupancyIn, Sud, Tank } from "../api/types";
import {
  STAGE_LABEL,
  batchRemainingHl,
  formatHl,
  sudNumberLabel,
} from "../domain";

interface ReplanDialogProps {
  sud: Sud;
  tanks: Tank[];
  sude: Sud[];
  onClose: () => void;
  onDone: (updated: Sud) => void;
}

interface Station {
  tankId: string;
  von: string;
}

function toLocalInputValue(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const WEEK_MS = 7 * 86_400_000;

/** Tankevolution eines Suds (Stefan, 2026-08-06): typischerweise Gärtank →
 * Lagertank → Ausschank/Fass, aber nicht immer — das Bier darf auch im
 * Gärtank bleiben (der kann als Lagertank weiterdienen). Deshalb stehen
 * hier ALLE Tanks zur Wahl; die Stufe kommt aus dem gewählten Tank. Das
 * Ende einer Station ist der Start der nächsten; die letzte darf offen
 * bleiben. Stationen lassen sich anfügen und entfernen — gleiches Prinzip
 * wie die Aufteilungszeilen beim Umdrücken. */
export function ReplanDialog({
  sud,
  tanks,
  sude,
  onClose,
  onDone,
}: ReplanDialogProps) {
  const remaining = batchRemainingHl(sud, sude);
  const sorted = useMemo(
    () =>
      [...sud.occupancies].sort(
        (a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime(),
      ),
    [sud.occupancies],
  );

  const [stationen, setStationen] = useState<Station[]>(() =>
    sorted.map((o) => ({
      tankId: o.tank_id,
      von: toLocalInputValue(new Date(o.start_at)),
    })),
  );
  const [bis, setBis] = useState(() => {
    const last = sorted[sorted.length - 1];
    return last?.end_at ? toLocalInputValue(new Date(last.end_at)) : "";
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tankById = useMemo(() => new Map(tanks.map((t) => [t.id, t])), [tanks]);

  // Volle Tankliste; nur zu kleine Nicht-Ausschank-Tanks fliegen raus
  // (Ausschank blendet und prüft serverseitig das Headroom).
  const candidatesFor = (current: string) =>
    tanks.filter(
      (t) =>
        t.id === current ||
        (t.active && (t.stage === "ausschank" || t.capacity_hl >= remaining)),
    );

  const setStation = (index: number, patch: Partial<Station>) =>
    setStationen((prev) =>
      prev.map((s, i) => (i === index ? { ...s, ...patch } : s)),
    );

  const addStation = () =>
    setStationen((prev) => {
      const lastVon = prev[prev.length - 1]?.von;
      const von = lastVon
        ? toLocalInputValue(new Date(new Date(lastVon).getTime() + WEEK_MS))
        : toLocalInputValue(new Date());
      return [...prev, { tankId: "", von }];
    });

  const removeStation = (index: number) =>
    setStationen((prev) => prev.filter((_, i) => i !== index));

  const starts = stationen.map((s) => new Date(s.von).getTime());
  const datesOk =
    starts.every((t) => Number.isFinite(t)) &&
    starts.every((t, i) => i === 0 || t > starts[i - 1]) &&
    (bis === "" || new Date(bis).getTime() > starts[starts.length - 1]);
  const tanksOk = stationen.every((s) => s.tankId !== "");
  const canSubmit = stationen.length > 0 && tanksOk && datesOk;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);

    const payload: ScheduleOccupancyIn[] = stationen.map((s, i) => {
      const tank = tankById.get(s.tankId)!;
      const next = stationen[i + 1];
      const end = next
        ? new Date(next.von).toISOString()
        : bis
          ? new Date(bis).toISOString()
          : null;
      return {
        tank_id: s.tankId,
        stage: tank.stage,
        start_at: new Date(s.von).toISOString(),
        end_at: end,
        volume_hl: tank.stage === "ausschank" ? remaining : null,
      };
    });

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
          {formatHl(remaining)} · Ende einer Station = Start der nächsten
        </p>

        {stationen.map((station, i) => {
          const tank = tankById.get(station.tankId);
          return (
            <div className="station" key={i}>
              <label>
                Station {i + 1}
                {tank ? ` · ${STAGE_LABEL[tank.stage]}` : ""}
                <select
                  aria-label={`Station ${i + 1}`}
                  value={station.tankId}
                  onChange={(e) => setStation(i, { tankId: e.target.value })}
                  required
                >
                  <option value="">— Tank wählen —</option>
                  {candidatesFor(station.tankId).map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} ({STAGE_LABEL[t.stage]}, {formatHl(t.capacity_hl)})
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Von
                <input
                  type="datetime-local"
                  aria-label={`Von ${i + 1}`}
                  value={station.von}
                  onChange={(e) => setStation(i, { von: e.target.value })}
                  required
                />
              </label>
              {stationen.length > 1 && (
                <button
                  type="button"
                  className="secondary"
                  aria-label={`Station ${i + 1} entfernen`}
                  onClick={() => removeStation(i)}
                >
                  ✕
                </button>
              )}
            </div>
          );
        })}

        <button type="button" className="secondary" onClick={addStation}>
          + Station
        </button>

        <label>
          Ende der letzten Station (leer = offen)
          <input
            type="datetime-local"
            aria-label="Ende der letzten Station"
            value={bis}
            onChange={(e) => setBis(e.target.value)}
          />
        </label>

        {!datesOk && stationen.length > 0 && (
          <div className="error">
            Die Stationen müssen zeitlich aufeinander folgen.
          </div>
        )}
        {error && <div className="error">{error}</div>}

        <div className="dialog-actions">
          <button type="button" onClick={onClose} disabled={submitting}>
            Abbrechen
          </button>
          <button type="submit" disabled={!canSubmit || submitting}>
            {submitting ? "Speichere …" : "Umplanen"}
          </button>
        </div>
      </form>
    </div>
  );
}
