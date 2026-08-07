import { useMemo, useState } from "react";

import type { Recipe, Sud } from "../api/types";
import { formatDate, formatHl, formatZahl } from "../domain";

interface EinkaufslisteProps {
  sude: Sud[];
  recipes: Recipe[];
}

function isoDate(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function fmtKg(kg: number): string {
  return `${formatZahl(kg)} kg`;
}

function fmtGramm(g: number): string {
  return g >= 1000 ? `${(g / 1000).toFixed(1).replace(".", ",")} kg` : `${g} g`;
}

/** Einkaufsliste (Stefan, 2026-08-05): alle Sude eines Zeitraums (Sudtag)
 * und die aufsummierten Malz- und Hopfenmengen aus ihren Rezepten. Jeder
 * Sud zählt einzeln — auch Merge-Partner werden ja einzeln gebraut. */
export function Einkaufsliste({ sude, recipes }: EinkaufslisteProps) {
  const heute = new Date();
  const [von, setVon] = useState(isoDate(heute));
  const [bis, setBis] = useState(
    isoDate(new Date(heute.getTime() + 30 * 86_400_000)),
  );

  const recipeById = useMemo(
    () => new Map(recipes.map((r) => [r.id, r])),
    [recipes],
  );

  // brew_date ist "YYYY-MM-DD" — String-Vergleich reicht.
  const imZeitraum = useMemo(
    () =>
      sude
        .filter((s) => (!von || s.brew_date >= von) && (!bis || s.brew_date <= bis))
        .sort((a, b) => a.brew_date.localeCompare(b.brew_date)),
    [sude, von, bis],
  );

  const { malze, hopfen } = useMemo(() => {
    const malzMap = new Map<string, { name: string; maelzerei: string; kg: number }>();
    const hopfenMap = new Map<string, number>();
    for (const sud of imZeitraum) {
      const recipe = recipeById.get(sud.recipe_id);
      if (!recipe) continue;
      for (const m of recipe.malts ?? []) {
        const key = `${m.name}|${m.maelzerei ?? ""}`;
        const entry = malzMap.get(key) ?? {
          name: m.name,
          maelzerei: m.maelzerei ?? "",
          kg: 0,
        };
        entry.kg += m.kg;
        malzMap.set(key, entry);
      }
      for (const g of recipe.hop_gaben ?? []) {
        hopfenMap.set(g.name, (hopfenMap.get(g.name) ?? 0) + g.gramm);
      }
    }
    return {
      malze: [...malzMap.values()].sort((a, b) => b.kg - a.kg),
      hopfen: [...hopfenMap.entries()]
        .map(([name, gramm]) => ({ name, gramm }))
        .sort((a, b) => b.gramm - a.gramm),
    };
  }, [imZeitraum, recipeById]);

  return (
    <div className="einkauf">
      <section>
        <h2>Zeitraum</h2>
        <div className="einkauf-zeitraum">
          <label>
            Von
            <input
              type="date"
              value={von}
              onChange={(e) => setVon(e.target.value)}
            />
          </label>
          <label>
            Bis
            <input
              type="date"
              value={bis}
              onChange={(e) => setBis(e.target.value)}
            />
          </label>
        </div>
      </section>

      <section>
        <h2>Sude im Zeitraum ({imZeitraum.length})</h2>
        {imZeitraum.length === 0 && (
          <p className="empty">Keine Sude mit Sudtag in diesem Zeitraum.</p>
        )}
        {imZeitraum.map((sud) => (
          <div className="einkauf-row" key={sud.id}>
            <span>{formatDate(sud.brew_date)}</span>
            <span>
              {/* Jede Zeile ist EIN Braugang (15 hl) — auch beim Doppelsud
                  zählt hier nur die eigene Nummer (Stefan, 2026-08-06). */}
              {sud.recipe.beer_style} {sud.style_year_number}/
              {sud.brew_date.slice(0, 4)} · {sud.recipe.name}
            </span>
            <span className="muted">{formatHl(sud.volume_hl)}</span>
          </div>
        ))}
      </section>

      {malze.length > 0 && (
        <section>
          <h2>Malz</h2>
          {malze.map((m) => (
            <div className="einkauf-row" key={`${m.name}|${m.maelzerei}`}>
              <span>{m.name}</span>
              <span className="muted">{m.maelzerei}</span>
              <span>{fmtKg(m.kg)}</span>
            </div>
          ))}
          <div className="einkauf-row einkauf-summe">
            <span>Summe</span>
            <span />
            <span>{fmtKg(malze.reduce((sum, m) => sum + m.kg, 0))}</span>
          </div>
        </section>
      )}

      {hopfen.length > 0 && (
        <section>
          <h2>Hopfen</h2>
          {hopfen.map((h) => (
            <div className="einkauf-row" key={h.name}>
              <span>{h.name}</span>
              <span />
              <span>{fmtGramm(h.gramm)}</span>
            </div>
          ))}
          <div className="einkauf-row einkauf-summe">
            <span>Summe</span>
            <span />
            <span>{fmtGramm(hopfen.reduce((sum, h) => sum + h.gramm, 0))}</span>
          </div>
        </section>
      )}
    </div>
  );
}
