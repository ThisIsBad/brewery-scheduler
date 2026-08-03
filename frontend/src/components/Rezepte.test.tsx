import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";

import type { Recipe } from "../api/types";

vi.mock("../api/client", () => ({
  api: {
    createRecipe: vi.fn(),
  },
}));

import { api } from "../api/client";
import { Rezepte } from "./Rezepte";

const mocked = api as unknown as {
  createRecipe: ReturnType<typeof vi.fn>;
};

const recipe = (over: Partial<Recipe>): Recipe => ({
  id: "r-1",
  beer_style: "kellerbier",
  version: 1,
  name: "Kellerbier (Standard)",
  fermentation_duration_days: 7,
  open_fermentation_required: false,
  open_fermentation_duration_days: null,
  storage_duration_days: 21,
  max_storage_duration_days: 60,
  created_at: "2026-01-01T00:00:00Z",
  created_by: null,
  notes: null,
  ...over,
});

beforeEach(() => {
  mocked.createRecipe.mockReset().mockResolvedValue(recipe({ version: 2 }));
});

test("zeigt die aktuelle Version je Stil und die Historie mit Änderungen", () => {
  const v1 = recipe({ id: "r-1", version: 1, storage_duration_days: 21 });
  const v2 = recipe({
    id: "r-2",
    version: 2,
    storage_duration_days: 28,
    created_at: "2026-06-01T00:00:00Z",
    created_by: "Braumeister",
  });
  render(<Rezepte recipes={[v1, v2]} onReload={() => {}} />);

  // Version 2 ist die Karte, Version 1 steckt in der Historie.
  expect(screen.getByText("Version 2")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Historie \(2 Versionen\)/ }));
  expect(screen.getByText("Version 1")).toBeInTheDocument();
  expect(screen.getByText(/Lagerung: 21 → 28 Tage/)).toBeInTheDocument();
});

test("Neue Version legt version+1 über die API an", async () => {
  const onReload = vi.fn();
  render(<Rezepte recipes={[recipe({})]} onReload={onReload} />);

  fireEvent.click(screen.getByRole("button", { name: "Neue Version" }));
  const dialog = screen.getByRole("dialog", { name: "Neue Rezeptversion" });
  expect(
    within(dialog).getByText(/Speichern erzeugt eine neue Version/),
  ).toBeInTheDocument();

  fireEvent.change(within(dialog).getByLabelText("Lagerung (Tage)"), {
    target: { value: "28" },
  });
  fireEvent.change(
    within(dialog).getByLabelText("Was hat sich geändert? (Notiz)"),
    { target: { value: "Längere Lagerung nach Verkostung" } },
  );
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Version 2 anlegen" }),
  );

  await waitFor(() =>
    expect(mocked.createRecipe).toHaveBeenCalledWith({
      beer_style: "kellerbier",
      name: "Kellerbier (Standard)",
      fermentation_duration_days: 7,
      open_fermentation_required: false,
      open_fermentation_duration_days: null,
      storage_duration_days: 28,
      max_storage_duration_days: 60,
      notes: "Längere Lagerung nach Verkostung",
      created_by: null,
    }),
  );
  await waitFor(() => expect(onReload).toHaveBeenCalled());
});
