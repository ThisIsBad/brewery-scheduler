import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type {
  Recipe,
  ScheduleOccupancyIn,
  Sud,
  SudCreateIn,
  Tank,
  TankStage,
} from "../api/types";

interface NewSudDialogProps {
  open: boolean;
  recipes: Recipe[];
  tanks: Tank[];
  onClose: () => void;
  onCreated: (sud: Sud) => void;
}

export function NewSudDialog({
  open,
  recipes,
  tanks,
  onClose,
  onCreated,
}: NewSudDialogProps) {
  const [recipeId, setRecipeId] = useState<string>("");
  const [brewDate, setBrewDate] = useState<string>(today());
  const [scheduleNow, setScheduleNow] = useState<boolean>(true);
  const [tankId, setTankId] = useState<string>("");
  const [startAt, setStartAt] = useState<string>(roundedNowLocal());
  const [brewmaster, setBrewmaster] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Derive whether the chosen recipe needs the open fermentation tank.
  // Wheat must start in fermentation_open; everything else in
  // fermentation_closed. Reset the tank selection whenever the recipe
  // changes so the dropdown only shows compatible tanks.
  const recipe = recipes.find((r) => r.id === recipeId);
  const requiredStage: TankStage = recipe?.open_fermentation_required
    ? "fermentation_open"
    : "fermentation_closed";

  const compatibleTanks = useMemo(
    () => tanks.filter((t) => t.stage === requiredStage && t.active),
    [tanks, requiredStage],
  );

  useEffect(() => {
    if (!compatibleTanks.find((t) => t.id === tankId)) {
      setTankId(compatibleTanks[0]?.id ?? "");
    }
  }, [compatibleTanks, tankId]);

  if (!open) return null;

  const canSubmit =
    recipeId !== "" && brewDate !== "" && (!scheduleNow || tankId !== "");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload: SudCreateIn = {
        recipe_id: recipeId,
        brew_date: brewDate,
        brewmaster: brewmaster || undefined,
      };
      if (scheduleNow) {
        const occ: ScheduleOccupancyIn = {
          tank_id: tankId,
          stage: requiredStage,
          start_at: new Date(startAt).toISOString(),
          end_at: null,
        };
        payload.initial_occupancy = occ;
      }
      const created = await api.createSud(payload);
      onCreated(created);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="dialog-backdrop" role="dialog" aria-label="Neuer Sud">
      <form className="dialog" onSubmit={handleSubmit}>
        <h2>Neuer Sud</h2>

        <label>
          Rezept
          <select
            value={recipeId}
            onChange={(e) => setRecipeId(e.target.value)}
            required
          >
            <option value="">— wählen —</option>
            {recipes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} (v{r.version})
              </option>
            ))}
          </select>
        </label>

        <label>
          Sudtag
          <input
            type="date"
            value={brewDate}
            onChange={(e) => setBrewDate(e.target.value)}
            required
          />
        </label>

        <label>
          Braumeister*in (optional)
          <input
            type="text"
            maxLength={128}
            value={brewmaster}
            onChange={(e) => setBrewmaster(e.target.value)}
          />
        </label>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={scheduleNow}
            onChange={(e) => setScheduleNow(e.target.checked)}
          />
          Direkt einplanen (Gärtank + Startzeit)
        </label>

        {scheduleNow && (
          <>
            <label>
              {requiredStage === "fermentation_open"
                ? "Gärtank (offen)"
                : "Gärtank"}
              <select
                value={tankId}
                onChange={(e) => setTankId(e.target.value)}
                required
              >
                <option value="">— wählen —</option>
                {compatibleTanks.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name} ({t.capacity_hl} hl)
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
          </>
        )}

        {error && <div className="error">{error}</div>}

        <div className="dialog-actions">
          <button type="button" onClick={onClose} disabled={submitting}>
            Abbrechen
          </button>
          <button type="submit" disabled={!canSubmit || submitting}>
            {submitting ? "Speichere …" : "Anlegen"}
          </button>
        </div>
      </form>
    </div>
  );
}

function today(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function roundedNowLocal(): string {
  // <input type="datetime-local"> wants `YYYY-MM-DDTHH:MM` in local time.
  const d = new Date();
  d.setMinutes(0, 0, 0);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  const h = String(d.getHours()).padStart(2, "0");
  return `${y}-${m}-${day}T${h}:00`;
}
