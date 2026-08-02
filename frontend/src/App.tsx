import { useCallback, useEffect, useState } from "react";

import { api } from "./api/client";
import type { Recipe, ScheduleOccupancyIn, Sud, Tank } from "./api/types";
import { Kellerblick } from "./components/Kellerblick";
import { NewSudDialog } from "./components/NewSudDialog";
import { ScheduleBoard } from "./components/ScheduleBoard";

type View = "kellerblick" | "zeitplan";

export default function App() {
  const [tanks, setTanks] = useState<Tank[]>([]);
  const [sude, setSude] = useState<Sud[]>([]);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [view, setView] = useState<View>("kellerblick");

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [t, s, r] = await Promise.all([
        api.listTanks(),
        api.listSude(),
        api.listRecipes(),
      ]);
      setTanks(t);
      setSude(s);
      setRecipes(r);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const applySudUpdate = useCallback((updated: Sud) => {
    setSude((prev) => {
      const exists = prev.some((s) => s.id === updated.id);
      return exists
        ? prev.map((s) => (s.id === updated.id ? updated : s))
        : [...prev, updated];
    });
    setError(null);
  }, []);

  const handleMove = useCallback(
    async (
      sudId: string,
      occupancyId: string,
      nextTankId: string,
      nextStartMs: number,
    ) => {
      const sud = sude.find((s) => s.id === sudId);
      if (!sud) return;
      const moved = sud.occupancies.find((o) => o.id === occupancyId);
      if (!moved) return;

      const originalStart = new Date(moved.start_at).getTime();
      const durationMs = moved.end_at
        ? new Date(moved.end_at).getTime() - originalStart
        : null;
      const nextEnd =
        durationMs !== null ? new Date(nextStartMs + durationMs).toISOString() : null;

      const payload: ScheduleOccupancyIn[] = sud.occupancies.map((o) =>
        o.id === occupancyId
          ? {
              tank_id: nextTankId,
              stage: o.stage,
              start_at: new Date(nextStartMs).toISOString(),
              end_at: nextEnd,
              volume_hl: o.volume_hl,
            }
          : {
              tank_id: o.tank_id,
              stage: o.stage,
              start_at: o.start_at,
              end_at: o.end_at,
              volume_hl: o.volume_hl,
            },
      );

      try {
        const updated = await api.updateSchedule(sudId, { occupancies: payload });
        applySudUpdate(updated);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [sude, applySudUpdate],
  );

  return (
    <div className="app">
      <header className="app-header">
        <h1>Brauerei</h1>
        <nav className="tabs" aria-label="Ansicht">
          <button
            type="button"
            className={view === "kellerblick" ? "active" : ""}
            onClick={() => setView("kellerblick")}
          >
            Kellerblick
          </button>
          <button
            type="button"
            className={view === "zeitplan" ? "active" : ""}
            onClick={() => setView("zeitplan")}
          >
            Zeitplan
          </button>
        </nav>
        <button
          type="button"
          className="new-sud"
          onClick={() => setDialogOpen(true)}
          disabled={loading}
        >
          + Sud
        </button>
      </header>

      {error && <div className="error banner">{error}</div>}

      {view === "kellerblick" ? (
        <div className="app-scroll">
          {loading ? (
            <p className="empty">lade …</p>
          ) : (
            <Kellerblick tanks={tanks} sude={sude} onChanged={applySudUpdate} />
          )}
        </div>
      ) : (
        <div className="app-board">
          {tanks.length > 0 && (
            <ScheduleBoard tanks={tanks} sude={sude} onMoveOccupancy={handleMove} />
          )}
        </div>
      )}

      <NewSudDialog
        open={dialogOpen}
        recipes={recipes}
        tanks={tanks}
        onClose={() => setDialogOpen(false)}
        onCreated={applySudUpdate}
      />
    </div>
  );
}
