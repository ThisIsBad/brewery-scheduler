import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";

import type { Sud, Tank } from "./api/types";

vi.mock("./api/client", () => ({
  api: {
    listTanks: vi.fn(),
    listLocations: vi.fn(),
    listSude: vi.fn(),
    listRecipes: vi.fn(),
    transferSud: vi.fn(),
    ich: vi.fn(),
  },
}));

import { api } from "./api/client";
import App from "./App";

const mocked = api as unknown as {
  listTanks: ReturnType<typeof vi.fn>;
  listLocations: ReturnType<typeof vi.fn>;
  listSude: ReturnType<typeof vi.fn>;
  listRecipes: ReturnType<typeof vi.fn>;
  transferSud: ReturnType<typeof vi.fn>;
  ich: ReturnType<typeof vi.fn>;
};

const STORAGE_TANK: Tank = {
  id: "tank-s1",
  name: "S-30-1",
  location_id: "loc-1",
  stage: "storage",
  capacity_hl: 30,
  active: true,
  locked: false,
};

const A100: Tank = {
  id: "tank-a100",
  name: "A-100",
  location_id: "loc-1",
  stage: "ausschank",
  capacity_hl: 100,
  active: true,
  locked: false,
};

const lead: Sud = {
  id: "sud-1",
  recipe_id: "recipe-1",
  recipe: {
    id: "recipe-1",
    beer_style: "kellerbier",
    version: 1,
    name: "Kellerbier",
    fermentation_duration_days: 7,
    open_fermentation_required: false,
    open_fermentation_duration_days: null,
    storage_duration_days: 21,
    max_storage_duration_days: 60,
    created_at: "2026-01-01T00:00:00Z",
    created_by: null,
    notes: null,
  },
  brew_at: "2026-07-20T08:00:00Z",
  brew_date: "2026-07-20",
  status: "storing",
  notes: null,
  brewmaster: null,
  style_year_number: 1,
  global_number: 210,
  volume_hl: 15,
  merged_into_sud_id: null,
  occupancies: [
    {
      id: "occ-1",
      sud_id: "sud-1",
      tank_id: STORAGE_TANK.id,
      stage: "storage",
      start_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
      end_at: new Date(Date.now() + 4 * 86_400_000).toISOString(),
      volume_hl: null,
    },
  ],
  withdrawals: [],
};

test("zeigt Prozess-Warnungen aus einem Transfer als schließbares Banner", async () => {
  mocked.listTanks.mockResolvedValue([STORAGE_TANK, A100]);
  mocked.listLocations.mockResolvedValue([
    { id: "loc-1", name: "Hauptkeller", position: 1 },
  ]);
  mocked.listSude.mockResolvedValue([lead]);
  mocked.listRecipes.mockResolvedValue([]);
  mocked.ich.mockResolvedValue({ benutzer: "stefan" });
  mocked.transferSud.mockResolvedValue({
    ...lead,
    status: "in_ausschank",
    warnings: ["Gärzeit evtl. zu kurz — Testfall."],
  });

  render(<App />);

  fireEvent.click(await screen.findByRole("button", { name: "Umdrücken" }));
  const dialog = screen.getByRole("dialog", { name: "Umdrücken" });
  fireEvent.change(within(dialog).getByLabelText("Zieltank"), {
    target: { value: A100.id },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Umdrücken" }));

  await waitFor(() => expect(mocked.transferSud).toHaveBeenCalledOnce());
  // The banner (role=status) carries the warning; the card shows its own
  // warn note, so scope the assertions to the banner.
  const banner = await screen.findByRole("status");
  expect(within(banner).getByText(/Gärzeit/)).toBeInTheDocument();

  fireEvent.click(within(banner).getByRole("button", { name: "OK" }));
  expect(screen.queryByRole("status")).toBeNull();
});

test("altes Backend ohne /api/locations: App lädt trotzdem und nennt den Fix", async () => {
  mocked.listTanks.mockResolvedValue([STORAGE_TANK]);
  mocked.listSude.mockResolvedValue([lead]);
  mocked.listRecipes.mockResolvedValue([]);
  mocked.ich.mockResolvedValue({ benutzer: "stefan" });
  mocked.listLocations.mockRejectedValue(new Error("Not Found"));

  render(<App />);

  // Kellerblick kommt trotzdem hoch …
  expect(await screen.findByText("S-30-1")).toBeInTheDocument();
  // … und der Banner beschreibt den Zustand, statt eine Umgebung zu
  // raten: derselbe Fehler tritt auf dem Server auf, wo es weder ein
  // ./up noch einen Codespace gibt.
  expect(
    screen.getByText(/Standorte konnten nicht geladen werden/),
  ).toBeInTheDocument();
});
