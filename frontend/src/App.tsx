import { useCallback, useEffect, useState } from "react";

import { api } from "./api/client";
import { replay } from "./api/queue";
import type { Location, Recipe, ScheduleOccupancyIn, Sud, Tank } from "./api/types";
import { Einkaufsliste } from "./components/Einkaufsliste";
import { Kellerblick } from "./components/Kellerblick";
import { NewSudDialog } from "./components/NewSudDialog";
import { Rezepte } from "./components/Rezepte";
import type { View } from "./components/Navigation";
import { Navigation, Profil, VIEW_TITEL } from "./components/Navigation";
import { Tankverwaltung } from "./components/Tankverwaltung";
import { Verlauf } from "./components/Verlauf";
import { Warteschlange } from "./components/Warteschlange";
import { Zeitplan } from "./components/Zeitplan";

export default function App() {
  const [tanks, setTanks] = useState<Tank[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [sude, setSude] = useState<Sud[]>([]);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
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
      try {
        setLocations(await api.listLocations());
        setError(null);
      } catch {
        // Kann zweierlei heißen: frisch synchronisierte Entwicklung
        // (neues Frontend, altes Backend ohne /api/locations) oder ein
        // Gerät, das gerade keine Verbindung hat und aus dem Cache liest.
        // Die Meldung nennt deshalb den Zustand, nicht eine geratene
        // Umgebung — der alte Text schickte auf dem Server in die Irre.
        setLocations([]);
        setError(
          "Standorte konnten nicht geladen werden — angezeigte Daten können veraltet sein. App neu öffnen; bleibt es dabei, läuft der Server mit einem älteren Stand.",
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Queued offline mutations (issue #10) go out as soon as there is a
  // path to the server again: on app start, on the browser's online
  // event, and whenever the tab comes back into view — then refetch so
  // the cards show what the server actually booked. Refetch-on-visible
  // also covers the cellar round with the tab backgrounded in between.
  const syncUp = useCallback(async () => {
    await replay();
    void refresh();
  }, [refresh]);

  useEffect(() => {
    void syncUp();
    const onVisible = () => {
      if (document.visibilityState === "visible") void syncUp();
    };
    const onOnline = () => void syncUp();
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("online", onOnline);
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("online", onOnline);
    };
  }, [syncUp]);

  const applySudUpdate = useCallback((updated: Sud) => {
    setSude((prev) => {
      const exists = prev.some((s) => s.id === updated.id);
      return exists
        ? prev.map((s) => (s.id === updated.id ? updated : s))
        : [...prev, updated];
    });
    setError(null);
    // Process hints (e.g. active yeast into Ausschank) — the action went
    // through; the banner just tells the brewmaster what deviates.
    setWarnings(updated.warnings ?? []);
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

  // Ende/Dauer ändern (2026-08-06): nur end_at der gewählten Belegung
  // wandert — z. B. die Lagerung verlängern; der Start bleibt stehen.
  const handleResize = useCallback(
    async (sudId: string, occupancyId: string, nextEndMs: number) => {
      const sud = sude.find((s) => s.id === sudId);
      if (!sud) return;
      const payload: ScheduleOccupancyIn[] = sud.occupancies.map((o) => ({
        tank_id: o.tank_id,
        stage: o.stage,
        start_at: o.start_at,
        end_at:
          o.id === occupancyId ? new Date(nextEndMs).toISOString() : o.end_at,
        volume_hl: o.volume_hl,
      }));

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
        <h1>{VIEW_TITEL[view]}</h1>
        <Profil />
        <button
          type="button"
          className="new-sud"
          onClick={() => setDialogOpen(true)}
          disabled={loading}
        >
          + Sud
        </button>
      </header>

      <Warteschlange onReplayed={() => void refresh()} />
      {error && <div className="error banner">{error}</div>}
      {warnings.length > 0 && (
        <div className="warning banner" role="status">
          <div>
            {warnings.map((w) => (
              <p key={w}>⚠️ {w}</p>
            ))}
          </div>
          <button type="button" onClick={() => setWarnings([])}>
            OK
          </button>
        </div>
      )}

      {view === "kellerblick" && (
        <div className="app-scroll">
          {loading ? (
            <p className="empty">lade …</p>
          ) : (
            <Kellerblick tanks={tanks} sude={sude} onChanged={applySudUpdate} />
          )}
        </div>
      )}
      {view === "zeitplan" && (
        <div className="app-board">
          {tanks.length > 0 && (
            <Zeitplan
              tanks={tanks}
              sude={sude}
              onMoveOccupancy={handleMove}
              onResizeOccupancy={handleResize}
            />
          )}
        </div>
      )}
      {view === "tanks" && (
        <div className="app-scroll">
          {loading ? (
            <p className="empty">lade …</p>
          ) : (
            <Tankverwaltung
              tanks={tanks}
              locations={locations}
              onReload={() => void refresh()}
            />
          )}
        </div>
      )}
      {view === "rezepte" && (
        <div className="app-scroll">
          {loading ? (
            <p className="empty">lade …</p>
          ) : (
            <Rezepte recipes={recipes} onReload={() => void refresh()} />
          )}
        </div>
      )}
      {view === "einkauf" && (
        <div className="app-scroll">
          {loading ? (
            <p className="empty">lade …</p>
          ) : (
            <Einkaufsliste sude={sude} recipes={recipes} />
          )}
        </div>
      )}

      {view === "verlauf" && (
        <div className="app-scroll">
          <Verlauf sude={sude} tanks={tanks} />
        </div>
      )}

      <Navigation view={view} onView={setView} />

      {dialogOpen && (
        <NewSudDialog
          open
          recipes={recipes}
          tanks={tanks}
          onClose={() => setDialogOpen(false)}
          onCreated={applySudUpdate}
        />
      )}
    </div>
  );
}
