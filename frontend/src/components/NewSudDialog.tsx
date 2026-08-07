import { useEffect, useMemo, useState } from "react";

import { api } from "../api/client";
import type {
  Recipe,
  RecipeOverridesIn,
  ScheduleOccupancyIn,
  Sud,
  SudCreateIn,
  Tank,
  TankStage,
} from "../api/types";
import { formatHl, latestRecipes } from "../domain";

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
  const [brewAt, setBrewAt] = useState<string>(roundedNowLocal());
  const [scheduleNow, setScheduleNow] = useState<boolean>(true);
  const [tankId, setTankId] = useState<string>("");
  // Fermentation start defaults to Brauzeit + 8 h (the brewhouse day) and
  // follows the brew time until the brewmaster edits it deliberately.
  const [startAt, setStartAt] = useState<string>(plusHours(roundedNowLocal(), 8));
  const [startTouched, setStartTouched] = useState<boolean>(false);
  const [brewmaster, setBrewmaster] = useState<string>("");
  // Per-Sud deviations from the recipe (Phase 3): collapsed by default,
  // the common case follows the recipe untouched.
  const [showOverrides, setShowOverrides] = useState<boolean>(false);
  const [ovFerm, setOvFerm] = useState<string>("");
  const [ovStorage, setOvStorage] = useState<string>("");
  const [ovOpen, setOvOpen] = useState<string>("");
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // New Sude always use the latest recipe version per style (issue #4);
  // older versions stay linked to their existing Sude only. Archived
  // beers („Frühere Biere") are not offered.
  const selectableRecipes = latestRecipes(
    recipes.filter((r) => r.active !== false),
  ) as Recipe[];

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

  // Overrides are deviations from ONE recipe — switching the recipe must
  // not carry another style's numbers along (or a hidden open-fermentation
  // value the new recipe's form never showed).
  useEffect(() => {
    setOvFerm("");
    setOvStorage("");
    setOvOpen("");
  }, [recipeId]);

  if (!open) return null;

  const canSubmit =
    recipeId !== "" && brewAt !== "" && (!scheduleNow || tankId !== "");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const overrides: RecipeOverridesIn = {};
      if (showOverrides) {
        if (parseFloat(ovFerm) > 0)
          overrides.fermentation_duration_days = parseFloat(ovFerm);
        if (parseFloat(ovStorage) > 0)
          overrides.storage_duration_days = parseFloat(ovStorage);
        if (recipe?.open_fermentation_required && parseFloat(ovOpen) > 0)
          overrides.open_fermentation_duration_days = parseFloat(ovOpen);
      }
      const payload: SudCreateIn = {
        recipe_id: recipeId,
        brew_at: new Date(brewAt).toISOString(),
        brewmaster: brewmaster || undefined,
        recipe_overrides:
          Object.keys(overrides).length > 0 ? overrides : undefined,
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
            {selectableRecipes.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} (v{r.version})
              </option>
            ))}
          </select>
        </label>

        <label className="checkbox">
          <input
            type="checkbox"
            checked={showOverrides}
            onChange={(e) => setShowOverrides(e.target.checked)}
          />
          Abweichungen vom Rezept für diesen Sud
        </label>
        {showOverrides && recipe && (
          <>
            {recipe.open_fermentation_required && (
              <label>
                Offene Gärung (Tage, Rezept:{" "}
                {recipe.open_fermentation_duration_days ?? "—"})
                <input
                  type="number"
                  min="0.5"
                  step="0.5"
                  placeholder="wie Rezept"
                  value={ovOpen}
                  onChange={(e) => setOvOpen(e.target.value)}
                />
              </label>
            )}
            <label>
              Gärung (Tage, Rezept: {recipe.fermentation_duration_days})
              <input
                type="number"
                min="0.5"
                step="0.5"
                placeholder="wie Rezept"
                value={ovFerm}
                onChange={(e) => setOvFerm(e.target.value)}
              />
            </label>
            <label>
              Lagerung (Tage, Rezept: {recipe.storage_duration_days})
              <input
                type="number"
                min="0.5"
                step="0.5"
                placeholder="wie Rezept"
                value={ovStorage}
                onChange={(e) => setOvStorage(e.target.value)}
              />
            </label>
          </>
        )}

        <label>
          Brauzeit (Tag + Uhrzeit)
          <input
            type="datetime-local"
            value={brewAt}
            onChange={(e) => {
              const next = e.target.value;
              setBrewAt(next);
              if (!startTouched && next) setStartAt(plusHours(next, 8));
            }}
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
                onChange={(e) => {
                  setStartTouched(true);
                  setStartAt(e.target.value);
                }}
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

function plusHours(localValue: string, hours: number): string {
  const d = new Date(localValue);
  d.setTime(d.getTime() + hours * 3_600_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
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
