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
  expect(screen.getByText(/Lagerung: 21 Tage → 28 Tage/)).toBeInTheDocument();
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
      malts: [],
      hop_gaben: [],
      yeast: null,
      original_gravity_plato: null,
      ibu: null,
      color_ebc: null,
      notes: "Längere Lagerung nach Verkostung",
      created_by: null,
    }),
  );
  await waitFor(() => expect(onReload).toHaveBeenCalled());
});

test("erfasst Schüttung, Hopfengaben, Hefe und Brauwerte in der neuen Version", async () => {
  const onReload = vi.fn();
  render(<Rezepte recipes={[recipe({})]} onReload={onReload} />);

  fireEvent.click(screen.getByRole("button", { name: "Neue Version" }));
  const dialog = screen.getByRole("dialog", { name: "Neue Rezeptversion" });

  fireEvent.click(within(dialog).getByRole("button", { name: "+ Malz" }));
  fireEvent.change(within(dialog).getByLabelText("Malz 1"), {
    target: { value: "Pilsner Malz" },
  });
  fireEvent.change(within(dialog).getByLabelText("Malz 1 kg"), {
    target: { value: "250" },
  });

  fireEvent.click(within(dialog).getByRole("button", { name: "+ Hopfengabe" }));
  fireEvent.change(within(dialog).getByLabelText("Hopfen 1"), {
    target: { value: "Perle" },
  });
  fireEvent.change(within(dialog).getByLabelText("Hopfen 1 g"), {
    target: { value: "1800" },
  });
  fireEvent.change(within(dialog).getByLabelText("Hopfen 1 min"), {
    target: { value: "60" },
  });

  fireEvent.change(within(dialog).getByLabelText("Hefe"), {
    target: { value: "W-34/70" },
  });
  fireEvent.change(within(dialog).getByLabelText("Stammwürze (°P)"), {
    target: { value: "12.5" },
  });
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Version 2 anlegen" }),
  );

  await waitFor(() => expect(mocked.createRecipe).toHaveBeenCalledOnce());
  const payload = mocked.createRecipe.mock.calls[0][0];
  expect(payload.malts).toEqual([{ name: "Pilsner Malz", kg: 250 }]);
  expect(payload.hop_gaben).toEqual([
    { name: "Perle", gramm: 1800, kochzeit_min: 60 },
  ]);
  expect(payload.yeast).toBe("W-34/70");
  expect(payload.original_gravity_plato).toBe(12.5);
});

test("zeigt Schüttung und Brauwerte auf der Rezeptkarte", () => {
  const voll = recipe({
    malts: [{ name: "Pilsner Malz", kg: 250 }],
    hop_gaben: [{ name: "Perle", gramm: 1800, kochzeit_min: 60 }],
    yeast: "W-34/70",
    original_gravity_plato: 12.5,
    ibu: 24,
    color_ebc: 11,
  });
  render(<Rezepte recipes={[voll]} onReload={() => {}} />);

  expect(screen.getByText(/Pilsner Malz 250 kg/)).toBeInTheDocument();
  expect(screen.getByText(/Perle 1800 g @ 60 min/)).toBeInTheDocument();
  expect(screen.getByText(/Hefe: W-34\/70 · 12.5 °P · 24 IBU · 11 EBC/)).toBeInTheDocument();
});
