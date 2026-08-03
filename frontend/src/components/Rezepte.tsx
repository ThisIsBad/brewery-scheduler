import { useState } from "react";

import { api } from "../api/client";
import type { BeerStyle, Recipe } from "../api/types";
import { STYLE_LABEL, formatDate } from "../domain";

interface RezepteProps {
  recipes: Recipe[];
  onReload: () => void;
}

const STYLES: BeerStyle[] = ["kellerbier", "wheat", "festbier", "special"];

export function Rezepte({ recipes, onReload }: RezepteProps) {
  const [editing, setEditing] = useState<Recipe | null>(null);
  const [historyStyle, setHistoryStyle] = useState<BeerStyle | null>(null);

  return (
    <div className="rezepte">
      {STYLES.map((style) => {
        const versions = recipes
          .filter((r) => r.beer_style === style)
          .sort((a, b) => b.version - a.version);
        const current = versions[0];
        if (!current) return null;
        return (
          <section key={style}>
            <h2>{STYLE_LABEL[style]}</h2>
            <article className="card">
              <header>
                <strong>{current.name}</strong>
                <span className="muted">Version {current.version}</span>
              </header>
              <div className="card-body">
                <div className="muted">
                  {current.open_fermentation_required &&
                    `Offene Gärung ${fmtDays(current.open_fermentation_duration_days)} · `}
                  Gärung {fmtDays(current.fermentation_duration_days)} · Lagerung{" "}
                  {fmtDays(current.storage_duration_days)} (max.{" "}
                  {fmtDays(current.max_storage_duration_days)})
                </div>
                {current.notes && <div className="muted">{current.notes}</div>}
              </div>
              <footer>
                <button type="button" onClick={() => setEditing(current)}>
                  Neue Version
                </button>
                {versions.length > 1 && (
                  <button
                    type="button"
                    className="secondary"
                    onClick={() =>
                      setHistoryStyle(historyStyle === style ? null : style)
                    }
                  >
                    {historyStyle === style
                      ? "Historie ausblenden"
                      : `Historie (${versions.length} Versionen)`}
                  </button>
                )}
              </footer>
            </article>

            {historyStyle === style &&
              versions.slice(1).map((older, i) => {
                const newer = versions[i];
                return (
                  <article className="card history" key={older.id}>
                    <header>
                      <strong>Version {older.version}</strong>
                      <span className="muted">
                        bis {formatDate(newer.created_at)}
                        {older.created_by ? ` · ${older.created_by}` : ""}
                      </span>
                    </header>
                    <div className="card-body">
                      <div className="muted">
                        {diffLines(older, newer).map((line) => (
                          <div key={line}>{line}</div>
                        ))}
                      </div>
                    </div>
                  </article>
                );
              })}
          </section>
        );
      })}

      {editing && (
        <RecipeVersionDialog
          base={editing}
          onClose={() => setEditing(null)}
          onDone={() => {
            setEditing(null);
            onReload();
          }}
        />
      )}
    </div>
  );
}

function fmtDays(value: number | null): string {
  if (value === null) return "—";
  return `${value % 1 === 0 ? value : value.toFixed(1)} Tage`;
}

/** What changed from `older` to `newer` — the per-version history line. */
function diffLines(older: Recipe, newer: Recipe): string[] {
  const fields: [keyof Recipe, string][] = [
    ["name", "Name"],
    ["fermentation_duration_days", "Gärung"],
    ["open_fermentation_duration_days", "Offene Gärung"],
    ["storage_duration_days", "Lagerung"],
    ["max_storage_duration_days", "Max. Lagerung"],
  ];
  const lines = fields
    .filter(([key]) => older[key] !== newer[key])
    .map(([key, label]) => {
      if (key === "name") return `${label}: „${older[key]}“ → „${newer[key]}“`;
      return `${label}: ${older[key] ?? "—"} → ${newer[key] ?? "—"} Tage`;
    });
  return lines.length > 0 ? lines : ["Keine Wertänderung (nur Notizen)."];
}

interface RecipeVersionDialogProps {
  base: Recipe;
  onClose: () => void;
  onDone: () => void;
}

function RecipeVersionDialog({ base, onClose, onDone }: RecipeVersionDialogProps) {
  const [name, setName] = useState(base.name);
  const [ferm, setFerm] = useState(String(base.fermentation_duration_days));
  const [openRequired, setOpenRequired] = useState(base.open_fermentation_required);
  const [openDays, setOpenDays] = useState(
    base.open_fermentation_duration_days !== null
      ? String(base.open_fermentation_duration_days)
      : "",
  );
  const [storage, setStorage] = useState(String(base.storage_duration_days));
  const [maxStorage, setMaxStorage] = useState(
    String(base.max_storage_duration_days),
  );
  const [notes, setNotes] = useState("");
  const [createdBy, setCreatedBy] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit =
    name.trim() !== "" &&
    parseFloat(ferm) > 0 &&
    parseFloat(storage) > 0 &&
    parseFloat(maxStorage) > 0 &&
    (!openRequired || parseFloat(openDays) > 0);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.createRecipe({
        beer_style: base.beer_style,
        name: name.trim(),
        fermentation_duration_days: parseFloat(ferm),
        open_fermentation_required: openRequired,
        open_fermentation_duration_days: openRequired
          ? parseFloat(openDays)
          : null,
        storage_duration_days: parseFloat(storage),
        max_storage_duration_days: parseFloat(maxStorage),
        notes: notes.trim() || null,
        created_by: createdBy.trim() || null,
      });
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

  return (
    <div
      className="dialog-backdrop"
      role="dialog"
      aria-label="Neue Rezeptversion"
    >
      <form className="dialog" onSubmit={handleSubmit}>
        <h2>
          {STYLE_LABEL[base.beer_style]}: Version {base.version + 1}
        </h2>
        <p className="muted">
          Rezepte sind unveränderlich — das Speichern erzeugt eine neue
          Version. Bereits geplante Sude behalten ihre bisherige Version.
        </p>

        <label>
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={128}
            required
          />
        </label>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={openRequired}
            onChange={(e) => setOpenRequired(e.target.checked)}
          />
          Offene Gärung erforderlich
        </label>
        {openRequired && (
          <label>
            Offene Gärung (Tage)
            <input
              type="number"
              min="0.5"
              step="0.5"
              value={openDays}
              onChange={(e) => setOpenDays(e.target.value)}
              required
            />
          </label>
        )}
        <label>
          Gärung (Tage)
          <input
            type="number"
            min="0.5"
            step="0.5"
            value={ferm}
            onChange={(e) => setFerm(e.target.value)}
            required
          />
        </label>
        <label>
          Lagerung (Tage)
          <input
            type="number"
            min="0.5"
            step="0.5"
            value={storage}
            onChange={(e) => setStorage(e.target.value)}
            required
          />
        </label>
        <label>
          Max. Lagerung (Tage)
          <input
            type="number"
            min="0.5"
            step="0.5"
            value={maxStorage}
            onChange={(e) => setMaxStorage(e.target.value)}
            required
          />
        </label>
        <label>
          Was hat sich geändert? (Notiz)
          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            maxLength={500}
          />
        </label>
        <label>
          Geändert von (optional)
          <input
            value={createdBy}
            onChange={(e) => setCreatedBy(e.target.value)}
            maxLength={128}
          />
        </label>

        {error && <div className="error">{error}</div>}

        <div className="dialog-actions">
          <button type="button" onClick={onClose} disabled={submitting}>
            Abbrechen
          </button>
          <button type="submit" disabled={!canSubmit || submitting}>
            {submitting ? "Speichere …" : `Version ${base.version + 1} anlegen`}
          </button>
        </div>
      </form>
    </div>
  );
}
