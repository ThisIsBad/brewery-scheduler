import { useState } from "react";

import { api } from "../api/client";
import type {
  BeerStyle,
  Hopfengabe,
  Maischrast,
  Malz,
  Recipe,
} from "../api/types";
import { STYLE_LABEL, formatDate } from "../domain";

interface RezepteProps {
  recipes: Recipe[];
  onReload: () => void;
}

export function Rezepte({ recipes, onReload }: RezepteProps) {
  const [editing, setEditing] = useState<Recipe | null>(null);
  const [creating, setCreating] = useState(false);
  const [historyStyle, setHistoryStyle] = useState<BeerStyle | null>(null);
  const [showFormer, setShowFormer] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Styles come from the data — the brewery names its beers freely.
  // Archived styles („Frühere Biere", wie in der Excel) sit in their own
  // collapsed section.
  const styles = [...new Set(recipes.map((r) => r.beer_style))];
  const latestOf = (style: BeerStyle) =>
    recipes
      .filter((r) => r.beer_style === style)
      .sort((a, b) => b.version - a.version)[0];
  const activeStyles = styles.filter((s) => latestOf(s)?.active !== false);
  const formerStyles = styles.filter((s) => latestOf(s)?.active === false);

  const setStyleActive = async (style: BeerStyle, active: boolean) => {
    setError(null);
    try {
      await api.setRecipeStyleActive({ beer_style: style, active });
      onReload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const renderStyle = (style: BeerStyle, former: boolean) => {
    const versions = recipes
      .filter((r) => r.beer_style === style)
      .sort((a, b) => b.version - a.version);
    const current = versions[0];
    if (!current) return null;
    return (
      <section key={style}>
        <h2>{STYLE_LABEL[style] ?? style}</h2>
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
                      .map(
                        (m) =>
                          `${m.name} ${m.kg} kg${m.maelzerei ? ` (${m.maelzerei})` : ""}`,
                      )
                      .join(" · ")}
                  </div>
                )}
                {(current.wasser?.hauptguss_hl != null ||
                  (current.wasser?.nachguss_hl?.length ?? 0) > 0) && (
                  <div className="muted">
                    Wasser:{" "}
                    {[
                      current.wasser?.hauptguss_hl != null
                        ? `Hauptguss ${current.wasser.hauptguss_hl} hl`
                        : null,
                      (current.wasser?.nachguss_hl?.length ?? 0) > 0
                        ? `Nachgüsse ${current.wasser!.nachguss_hl!.join(" + ")} hl`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                )}
                {(current.maischplan?.length ?? 0) > 0 && (
                  <div className="muted">
                    Maischen:{" "}
                    {current.maischplan!
                      .map(
                        (r) =>
                          `${r.schritt}${r.temp_c != null ? ` ${r.temp_c} °C` : ""}${
                            r.dauer_min != null ? ` (${r.dauer_min} min)` : ""
                          }`,
                      )
                      .join(" → ")}
                  </div>
                )}
                {(current.hop_gaben?.length ?? 0) > 0 && (
                  <div className="muted">
                    Hopfen:{" "}
                    {current.hop_gaben!
                      .map(
                        (g) =>
                          `${g.name} ${g.gramm} g — ${g.zeitpunkt}${
                            g.alpha_prozent != null
                              ? ` (${g.alpha_prozent} % α)`
                              : ""
                          }`,
                      )
                      .join(" · ")}
                  </div>
                )}
                {(current.yeast ||
                  current.original_gravity_plato != null ||
                  current.ibu != null ||
                  current.color_ebc != null ||
                  current.kochzeit_min != null ||
                  current.karbonisierung_g_l != null) && (
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
                      current.kochzeit_min != null
                        ? `Kochzeit ${current.kochzeit_min} min`
                        : null,
                      current.karbonisierung_g_l != null
                        ? `Karbonisierung ${current.karbonisierung_g_l} g/l`
                        : null,
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </div>
                )}
                {current.anstellhinweis && (
                  <div className="muted">Anstellen: {current.anstellhinweis}</div>
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
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setStyleActive(style, former)}
                >
                  {former ? "Reaktivieren" : "Archivieren"}
                </button>
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
  };

  return (
    <div className="rezepte">
      <button type="button" onClick={() => setCreating(true)}>
        + Neues Bier
      </button>
      {error && <div className="error">{error}</div>}

      {activeStyles.map((style) => renderStyle(style, false))}

      {formerStyles.length > 0 && (
        <section>
          <h2>
            <button
              type="button"
              className="secondary"
              onClick={() => setShowFormer((v) => !v)}
            >
              {showFormer
                ? "Frühere Biere ausblenden"
                : `Frühere Biere (${formerStyles.length})`}
            </button>
          </h2>
        </section>
      )}
      {showFormer && formerStyles.map((style) => renderStyle(style, true))}

      {(editing || creating) && (
        <RecipeVersionDialog
          base={editing}
          onClose={() => {
            setEditing(null);
            setCreating(false);
          }}
          onDone={() => {
            setEditing(null);
            setCreating(false);
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
    ["kochzeit_min", "Kochzeit", " min"],
    ["karbonisierung_g_l", "Karbonisierung", " g/l"],
    ["anstellhinweis", "Anstellen", ""],
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
  if (
    JSON.stringify(older.maischplan ?? []) !==
    JSON.stringify(newer.maischplan ?? [])
  ) {
    lines.push("Maischplan geändert");
  }
  if (
    JSON.stringify(older.wasser ?? null) !== JSON.stringify(newer.wasser ?? null)
  ) {
    lines.push("Wasser geändert");
  }
  return lines.length > 0 ? lines : ["Keine Wertänderung (nur Notizen)."];
}

interface RecipeVersionDialogProps {
  /** null = ein ganz neues Bier anlegen (Version 1 einer neuen Sorte). */
  base: Recipe | null;
  onClose: () => void;
  onDone: () => void;
}

function RecipeVersionDialog({ base, onClose, onDone }: RecipeVersionDialogProps) {
  const [style, setStyle] = useState(base?.beer_style ?? "");
  const [name, setName] = useState(base?.name ?? "");
  const [ferm, setFerm] = useState(
    base ? String(base.fermentation_duration_days) : "",
  );
  const [openRequired, setOpenRequired] = useState(
    base?.open_fermentation_required ?? false,
  );
  const [openDays, setOpenDays] = useState(
    base?.open_fermentation_duration_days != null
      ? String(base.open_fermentation_duration_days)
      : "",
  );
  const [storage, setStorage] = useState(
    base ? String(base.storage_duration_days) : "",
  );
  const [maxStorage, setMaxStorage] = useState(
    base ? String(base.max_storage_duration_days) : "",
  );
  const [malts, setMalts] = useState<
    { name: string; kg: string; maelzerei: string }[]
  >(
    (base?.malts ?? []).map((m) => ({
      name: m.name,
      kg: String(m.kg),
      maelzerei: m.maelzerei ?? "",
    })),
  );
  const [gaben, setGaben] = useState<
    { name: string; gramm: string; zeitpunkt: string; alpha: string }[]
  >(
    (base?.hop_gaben ?? []).map((g) => ({
      name: g.name,
      gramm: String(g.gramm),
      zeitpunkt: g.zeitpunkt,
      alpha: g.alpha_prozent != null ? String(g.alpha_prozent) : "",
    })),
  );
  const [rasten, setRasten] = useState<
    { schritt: string; temp: string; dauer: string }[]
  >(
    (base?.maischplan ?? []).map((r) => ({
      schritt: r.schritt,
      temp: r.temp_c != null ? String(r.temp_c) : "",
      dauer: r.dauer_min != null ? String(r.dauer_min) : "",
    })),
  );
  const [hauptguss, setHauptguss] = useState(
    base?.wasser?.hauptguss_hl != null ? String(base.wasser.hauptguss_hl) : "",
  );
  const [nachguesse, setNachguesse] = useState<string[]>(
    (base?.wasser?.nachguss_hl ?? []).map(String),
  );
  const [kochzeit, setKochzeit] = useState(
    base?.kochzeit_min != null ? String(base.kochzeit_min) : "",
  );
  const [karbo, setKarbo] = useState(
    base?.karbonisierung_g_l != null ? String(base.karbonisierung_g_l) : "",
  );
  const [anstell, setAnstell] = useState(base?.anstellhinweis ?? "");
  const [yeast, setYeast] = useState(base?.yeast ?? "");
  const [og, setOg] = useState(
    base?.original_gravity_plato != null
      ? String(base.original_gravity_plato)
      : "",
  );
  const [ibu, setIbu] = useState(base?.ibu != null ? String(base.ibu) : "");
  const [ebc, setEbc] = useState(
    base?.color_ebc != null ? String(base.color_ebc) : "",
  );
  const [notes, setNotes] = useState("");
  const [createdBy, setCreatedBy] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const maltsValid = malts.every((m) => m.name.trim() && parseFloat(m.kg) > 0);
  const gabenValid = gaben.every(
    (g) => g.name.trim() && parseFloat(g.gramm) > 0 && g.zeitpunkt.trim(),
  );
  const rastenValid = rasten.every(
    (r) =>
      r.schritt.trim() &&
      (r.temp === "" || parseFloat(r.temp) > 0) &&
      (r.dauer === "" || parseFloat(r.dauer) > 0),
  );
  const canSubmit =
    style.trim() !== "" &&
    name.trim() !== "" &&
    parseFloat(ferm) > 0 &&
    parseFloat(storage) > 0 &&
    parseFloat(maxStorage) > 0 &&
    (!openRequired || parseFloat(openDays) > 0) &&
    maltsValid &&
    gabenValid &&
    rastenValid;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const maltsOut: Malz[] = malts.map((m) => ({
        name: m.name.trim(),
        kg: parseFloat(m.kg),
        maelzerei: m.maelzerei.trim() || null,
      }));
      const gabenOut: Hopfengabe[] = gaben.map((g) => ({
        name: g.name.trim(),
        gramm: parseFloat(g.gramm),
        zeitpunkt: g.zeitpunkt.trim(),
        alpha_prozent: g.alpha ? parseFloat(g.alpha) : null,
      }));
      const rastenOut: Maischrast[] = rasten.map((r) => ({
        schritt: r.schritt.trim(),
        temp_c: r.temp ? parseFloat(r.temp) : null,
        dauer_min: r.dauer ? parseFloat(r.dauer) : null,
      }));
      const nachgussOut = nachguesse
        .map((n) => parseFloat(n))
        .filter((n) => n > 0);
      await api.createRecipe({
        beer_style: style.trim(),
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
        maischplan: rastenOut,
        wasser:
          hauptguss || nachgussOut.length > 0
            ? {
                hauptguss_hl: hauptguss ? parseFloat(hauptguss) : null,
                nachguss_hl: nachgussOut,
              }
            : null,
        yeast: yeast.trim() || null,
        original_gravity_plato: og ? parseFloat(og) : null,
        ibu: ibu ? parseFloat(ibu) : null,
        color_ebc: ebc ? parseFloat(ebc) : null,
        kochzeit_min: kochzeit ? parseFloat(kochzeit) : null,
        karbonisierung_g_l: karbo ? parseFloat(karbo) : null,
        anstellhinweis: anstell.trim() || null,
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
      aria-label={base ? "Neue Rezeptversion" : "Neues Bier"}
    >
      <form className="dialog" onSubmit={handleSubmit}>
        <h2>
          {base
            ? `${STYLE_LABEL[base.beer_style] ?? base.beer_style}: Version ${
                base.version + 1
              }`
            : "Neues Bier"}
        </h2>
        <p className="muted">
          Rezepte sind unveränderlich — das Speichern erzeugt eine neue
          Version. Bereits geplante Sude behalten ihre bisherige Version.
          Mengen gelten pro Standard-Sud (15 hl).
        </p>

        {!base && (
          <label>
            Sorte
            <input
              value={style}
              onChange={(e) => setStyle(e.target.value)}
              maxLength={64}
              placeholder="z. B. Rauchbier oder Collab Widder"
              required
            />
          </label>
        )}
        <label>
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={128}
            placeholder={base ? undefined : "z. B. Rauchbier Waltraut"}
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
            <input
              aria-label={`Malz ${i + 1} Mälzerei`}
              placeholder="Mälzerei"
              value={m.maelzerei}
              onChange={(e) =>
                setMalts((prev) =>
                  prev.map((x, j) =>
                    j === i ? { ...x, maelzerei: e.target.value } : x,
                  ),
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
          onClick={() =>
            setMalts((prev) => [...prev, { name: "", kg: "", maelzerei: "" }])
          }
        >
          + Malz
        </button>

        <h3>Wasser (hl)</h3>
        <label>
          Hauptguss (hl)
          <input
            type="number"
            min="0.5"
            step="0.5"
            value={hauptguss}
            onChange={(e) => setHauptguss(e.target.value)}
          />
        </label>
        {nachguesse.map((n, i) => (
          <div className="allocation-row" key={i}>
            <input
              aria-label={`Nachguss ${i + 1} (hl)`}
              type="number"
              min="0.5"
              step="0.5"
              placeholder={`Nachguss ${i + 1} (hl)`}
              value={n}
              onChange={(e) =>
                setNachguesse((prev) =>
                  prev.map((x, j) => (j === i ? e.target.value : x)),
                )
              }
            />
            <button
              type="button"
              className="secondary"
              onClick={() =>
                setNachguesse((prev) => prev.filter((_, j) => j !== i))
              }
            >
              ✕
            </button>
          </div>
        ))}
        <button
          type="button"
          className="secondary"
          onClick={() => setNachguesse((prev) => [...prev, ""])}
        >
          + Nachguss
        </button>

        <h3>Maischplan</h3>
        {rasten.map((r, i) => (
          <div className="allocation-row" key={i}>
            <input
              aria-label={`Rast ${i + 1} Schritt`}
              placeholder="Einmaischen / Rast / Abmaischen"
              value={r.schritt}
              onChange={(e) =>
                setRasten((prev) =>
                  prev.map((x, j) =>
                    j === i ? { ...x, schritt: e.target.value } : x,
                  ),
                )
              }
            />
            <input
              aria-label={`Rast ${i + 1} °C`}
              type="number"
              min="1"
              step="0.5"
              placeholder="°C"
              value={r.temp}
              onChange={(e) =>
                setRasten((prev) =>
                  prev.map((x, j) => (j === i ? { ...x, temp: e.target.value } : x)),
                )
              }
            />
            <input
              aria-label={`Rast ${i + 1} min`}
              type="number"
              min="1"
              step="1"
              placeholder="min"
              value={r.dauer}
              onChange={(e) =>
                setRasten((prev) =>
                  prev.map((x, j) =>
                    j === i ? { ...x, dauer: e.target.value } : x,
                  ),
                )
              }
            />
            <button
              type="button"
              className="secondary"
              onClick={() => setRasten((prev) => prev.filter((_, j) => j !== i))}
            >
              ✕
            </button>
          </div>
        ))}
        <button
          type="button"
          className="secondary"
          onClick={() =>
            setRasten((prev) => [...prev, { schritt: "", temp: "", dauer: "" }])
          }
        >
          + Rast
        </button>

        <label>
          Kochzeit (min)
          <input
            type="number"
            min="1"
            step="1"
            value={kochzeit}
            onChange={(e) => setKochzeit(e.target.value)}
          />
        </label>

        <h3>Hopfengaben (g pro Sud)</h3>
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
              aria-label={`Hopfen ${i + 1} % α`}
              type="number"
              min="0"
              step="0.1"
              placeholder="% α"
              value={g.alpha}
              onChange={(e) =>
                setGaben((prev) =>
                  prev.map((x, j) => (j === i ? { ...x, alpha: e.target.value } : x)),
                )
              }
            />
            <input
              aria-label={`Hopfen ${i + 1} Zeitpunkt`}
              placeholder="Kochbeginn / nach 55 min / Whirlpool"
              value={g.zeitpunkt}
              onChange={(e) =>
                setGaben((prev) =>
                  prev.map((x, j) =>
                    j === i ? { ...x, zeitpunkt: e.target.value } : x,
                  ),
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
            setGaben((prev) => [
              ...prev,
              { name: "", gramm: "", zeitpunkt: "", alpha: "" },
            ])
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
            placeholder="z. B. 3470 Wagner"
          />
        </label>
        <label>
          Anstellen / Gärführung
          <input
            value={anstell}
            onChange={(e) => setAnstell(e.target.value)}
            maxLength={256}
            placeholder="z. B. bei 9,5 Grad anstellen"
          />
        </label>
        <label>
          Karbonisierung (g/l)
          <input
            type="number"
            min="0.5"
            step="0.1"
            value={karbo}
            onChange={(e) => setKarbo(e.target.value)}
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
            {submitting
              ? "Speichere …"
              : base
                ? `Version ${base.version + 1} anlegen`
                : "Bier anlegen"}
          </button>
        </div>
      </form>
    </div>
  );
}
