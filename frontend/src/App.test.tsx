import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";

import type { Sud, Tank } from "./api/types";

vi.mock("./api/client", () => ({
  api: {
    listTanks: vi.fn(),
    listSude: vi.fn(),
    listRecipes: vi.fn(),
    transferSud: vi.fn(),
  },
}));

import { api } from "./api/client";
import App from "./App";

const mocked = api as unknown as {
  listTanks: ReturnType<typeof vi.fn>;
  listSude: ReturnType<typeof vi.fn>;
  listRecipes: ReturnType<typeof vi.fn>;
  transferSud: ReturnType<typeof vi.fn>;
};

const STORAGE_TANK: Tank = {
  id: "tank-s1",
  name: "S-30-1",
  cellar: "main",
  stage: "storage",
  capacity_hl: 30,
  active: true,
};

const A100: Tank = {
  id: "tank-a100",
  name: "A-100",
  cellar: "main",
  stage: "ausschank",
  capacity_hl: 100,
  active: true,
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
  },
  brew_at: "2026-07-20T08:00:00Z",
  brew_date: "2026-07-20",
  status: "storing",
  notes: null,
  brewmaster: null,
  style_year_number: 1,
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
  mocked.listSude.mockResolvedValue([lead]);
  mocked.listRecipes.mockResolvedValue([]);
  mocked.transferSud.mockResolvedValue({
    ...lead,
    status: "in_ausschank",
    warnings: ["Möglicherweise aktive Hefe im Ausschank: Testfall."],
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
  expect(within(banner).getByText(/aktive Hefe/)).toBeInTheDocument();

  fireEvent.click(within(banner).getByRole("button", { name: "OK" }));
  expect(screen.queryByRole("status")).toBeNull();
});
