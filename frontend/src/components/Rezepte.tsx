import { useState } from "react";

import { api } from "../api/client";
import type { BeerStyle, Hopfengabe, Malz, Recipe } from "../api/types";
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
                {(current.malts?.length ?? 0) > 0 && (
                  <div className="muted">
                    Schüttung:{" "}
                    {current.malts!
                      .map((m) => `${m.name} ${m.kg} kg`)
                      .join(" · ")}
                  </div>
                )}
                {(current.hop_gaben?.length ?? 0) > 0 && (
                  <div className="muted">
                    Hopfen:{" "}
                    {current.hop_gaben!
                      .map((g) => `${g.name} ${g.gramm} g @ ${g.kochzeit_min} min`)
                      .join(" · ")}
                  </div>
                )}
                {(current.yeast ||
                  current.original_gravity_plato != null ||
                  current.ibu != null ||
                  current.color_ebc != null) && (
                  <div className="muted">
                    {[
                      current.yeast ? `Hefe: ${current.yeast}` : null,
                      current.original_gravity_plato != null
                        ? `${current.original_gravity_plato} °P`
                        : null,
                      current.ibu != null ? `${current.ibu} IBU` : null,
                      current.color_ebc != null
                        ? `${current.color_ebc} EBC`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                )}
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
  const fields: [keyof Recipe, string, string][] = [
    ["name", "Name", ""],
    ["fermentation_duration_days", "Gärung", " Tage"],
    ["open_fermentation_duration_days", "Offene Gärung", " Tage"],
    ["storage_duration_days", "Lagerung", " Tage"],
    ["max_storage_duration_days", "Max. Lagerung", " Tage"],
    ["yeast", "Hefe", ""],
    ["original_gravity_plato", "Stammwürze", " °P"],
    ["ibu", "Bittere", " IBU"],
    ["color_ebc", "Farbe", " EBC"],
  ];
  const lines = fields
    .filter(([key]) => (older[key] ?? null) !== (newer[key] ?? null))
    .map(([key, label, unit]) => {
      const from = older[key] ?? "—";
      const to = newer[key] ?? "—";
      return `${label}: ${from}${unit} → ${to}${unit}`;
    });
  if (
    JSON.stringify(older.malts ?? []) !== JSON.stringify(newer.malts ?? [])
  ) {
    lines.push("Schüttung geändert");
  }
  if (
    JSON.stringify(older.hop_gaben ?? []) !==
    JSON.stringify(newer.hop_gaben ?? [])
  ) {
    lines.push("Hopfengaben geändert");
  }
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
  const [malts, setMalts] = useState<{ name: string; kg: string }[]>(
    (base.malts ?? []).map((m) => ({ name: m.name, kg: String(m.kg) })),
  );
  const [gaben, setGaben] = useState<
    { name: string; gramm: string; min: string }[]
  >(
    (base.hop_gaben ?? []).map((g) => ({
      name: g.name,
      gramm: String(g.gramm),
      min: String(g.kochzeit_min),
    })),
  );
  const [yeast, setYeast] = useState(base.yeast ?? "");
  const [og, setOg] = useState(
    base.original_gravity_plato != null ? String(base.original_gravity_plato) : "",
  );
  const [ibu, setIbu] = useState(base.ibu != null ? String(base.ibu) : "");
  const [ebc, setEbc] = useState(
    base.color_ebc != null ? String(base.color_ebc) : "",
  );
  const [notes, setNotes] = useState("");
  const [createdBy, setCreatedBy] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const maltsValid = malts.every((m) => m.name.trim() && parseFloat(m.kg) > 0);
  const gabenValid = gaben.every(
    (g) => g.name.trim() && parseFloat(g.gramm) > 0 && parseFloat(g.min) >= 0,
  );
  const canSubmit =
    name.trim() !== "" &&
    parseFloat(ferm) > 0 &&
    parseFloat(storage) > 0 &&
    parseFloat(maxStorage) > 0 &&
    (!openRequired || parseFloat(openDays) > 0) &&
    maltsValid &&
    gabenValid;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const maltsOut: Malz[] = malts.map((m) => ({
        name: m.name.trim(),
        kg: parseFloat(m.kg),
      }));
      const gabenOut: Hopfengabe[] = gaben.map((g) => ({
        name: g.name.trim(),
        gramm: parseFloat(g.gramm),
        kochzeit_min: parseFloat(g.min),
      }));
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
        malts: maltsOut,
        hop_gaben: gabenOut,
        yeast: yeast.trim() || null,
        original_gravity_plato: og ? parseFloat(og) : null,
        ibu: ibu ? parseFloat(ibu) : null,
        color_ebc: ebc ? parseFloat(ebc) : null,
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
          Mengen gelten pro Standard-Sud (15 hl).
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

        <h3>Schüttung (kg pro Sud)</h3>
        {malts.map((m, i) => (
          <div className="allocation-row" key={i}>
            <input
              aria-label={`Malz ${i + 1}`}
              placeholder="Malzsorte"
              value={m.name}
              onChange={(e) =>
                setMalts((prev) =>
                  prev.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)),
                )
              }
            />
            <input
              aria-label={`Malz ${i + 1} kg`}
              type="number"
              min="0.1"
              step="0.1"
              placeholder="kg"
              value={m.kg}
              onChange={(e) =>
                setMalts((prev) =>
                  prev.map((x, j) => (j === i ? { ...x, kg: e.target.value } : x)),
                )
              }
            />
            <button
              type="button"
              className="secondary"
              onClick={() => setMalts((prev) => prev.filter((_, j) => j !== i))}
            >
              ✕
            </button>
          </div>
        ))}
        <button
          type="button"
          className="secondary"
          onClick={() => setMalts((prev) => [...prev, { name: "", kg: "" }])}
        >
          + Malz
        </button>

        <h3>Hopfengaben (g pro Sud, Kochzeit in Minuten)</h3>
        {gaben.map((g, i) => (
          <div className="allocation-row" key={i}>
            <input
              aria-label={`Hopfen ${i + 1}`}
              placeholder="Hopfensorte"
              value={g.name}
              onChange={(e) =>
                setGaben((prev) =>
                  prev.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)),
                )
              }
            />
            <input
              aria-label={`Hopfen ${i + 1} g`}
              type="number"
              min="1"
              step="1"
              placeholder="g"
              value={g.gramm}
              onChange={(e) =>
                setGaben((prev) =>
                  prev.map((x, j) => (j === i ? { ...x, gramm: e.target.value } : x)),
                )
              }
            />
            <input
              aria-label={`Hopfen ${i + 1} min`}
              type="number"
              min="0"
              step="1"
              placeholder="min"
              value={g.min}
              onChange={(e) =>
                setGaben((prev) =>
                  prev.map((x, j) => (j === i ? { ...x, min: e.target.value } : x)),
                )
              }
            />
            <button
              type="button"
              className="secondary"
              onClick={() => setGaben((prev) => prev.filter((_, j) => j !== i))}
            >
              ✕
            </button>
          </div>
        ))}
        <button
          type="button"
          className="secondary"
          onClick={() =>
            setGaben((prev) => [...prev, { name: "", gramm: "", min: "" }])
          }
        >
          + Hopfengabe
        </button>

        <label>
          Hefe
          <input
            value={yeast}
            onChange={(e) => setYeast(e.target.value)}
            maxLength={128}
            placeholder="z. B. W-34/70"
          />
        </label>
        <label>
          Stammwürze (°P)
          <input
            type="number"
            min="1"
            step="0.1"
            value={og}
            onChange={(e) => setOg(e.target.value)}
          />
        </label>
        <label>
          Bittere (IBU)
          <input
            type="number"
            min="0"
            step="1"
            value={ibu}
            onChange={(e) => setIbu(e.target.value)}
          />
        </label>
        <label>
          Farbe (EBC)
          <input
            type="number"
            min="0"
            step="1"
            value={ebc}
            onChange={(e) => setEbc(e.target.value)}
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
