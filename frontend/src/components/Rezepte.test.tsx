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
      maischplan: [],
      wasser: null,
      yeast: null,
      original_gravity_plato: null,
      ibu: null,
      color_ebc: null,
      kochzeit_min: null,
      karbonisierung_g_l: null,
      anstellhinweis: null,
      notes: "Längere Lagerung nach Verkostung",
      created_by: null,
    }),
  );
  await waitFor(() => expect(onReload).toHaveBeenCalled());
});

test("erfasst den Brauzettel (Schüttung, Maische, Wasser, Hopfen) in der neuen Version", async () => {
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
  fireEvent.change(within(dialog).getByLabelText("Malz 1 Mälzerei"), {
    target: { value: "BM" },
  });

  fireEvent.change(within(dialog).getByLabelText("Hauptguss (hl)"), {
    target: { value: "11" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "+ Nachguss" }));
  fireEvent.change(within(dialog).getByLabelText("Nachguss 1 (hl)"), {
    target: { value: "5.5" },
  });

  fireEvent.click(within(dialog).getByRole("button", { name: "+ Rast" }));
  fireEvent.change(within(dialog).getByLabelText("Rast 1 Schritt"), {
    target: { value: "Einmaischen" },
  });
  fireEvent.change(within(dialog).getByLabelText("Rast 1 °C"), {
    target: { value: "61.5" },
  });
  fireEvent.change(within(dialog).getByLabelText("Rast 1 min"), {
    target: { value: "10" },
  });

  fireEvent.change(within(dialog).getByLabelText("Kochzeit (min)"), {
    target: { value: "70" },
  });

  fireEvent.click(within(dialog).getByRole("button", { name: "+ Hopfengabe" }));
  fireEvent.change(within(dialog).getByLabelText("Hopfen 1"), {
    target: { value: "Perle" },
  });
  fireEvent.change(within(dialog).getByLabelText("Hopfen 1 g"), {
    target: { value: "1800" },
  });
  fireEvent.change(within(dialog).getByLabelText("Hopfen 1 % α"), {
    target: { value: "6.5" },
  });
  fireEvent.change(within(dialog).getByLabelText("Hopfen 1 Zeitpunkt"), {
    target: { value: "Kochbeginn" },
  });

  fireEvent.change(within(dialog).getByLabelText("Hefe"), {
    target: { value: "3470 Wagner" },
  });
  fireEvent.change(within(dialog).getByLabelText("Anstellen / Gärführung"), {
    target: { value: "bei 9,5 Grad anstellen" },
  });
  fireEvent.change(within(dialog).getByLabelText("Karbonisierung (g/l)"), {
    target: { value: "4.5" },
  });
  fireEvent.change(within(dialog).getByLabelText("Stammwürze (°P)"), {
    target: { value: "12.5" },
  });
  expect(
    within(dialog).getByRole("button", { name: "Version 2 anlegen" }),
  ).toBeEnabled();
  fireEvent.click(
    within(dialog).getByRole("button", { name: "Version 2 anlegen" }),
  );

  await waitFor(() => expect(mocked.createRecipe).toHaveBeenCalledOnce());
  const payload = mocked.createRecipe.mock.calls[0][0];
  expect(payload.malts).toEqual([
    { name: "Pilsner Malz", kg: 250, maelzerei: "BM" },
  ]);
  expect(payload.hop_gaben).toEqual([
    { name: "Perle", gramm: 1800, zeitpunkt: "Kochbeginn", alpha_prozent: 6.5 },
  ]);
  expect(payload.maischplan).toEqual([
    { schritt: "Einmaischen", temp_c: 61.5, dauer_min: 10 },
  ]);
  expect(payload.wasser).toEqual({ hauptguss_hl: 11, nachguss_hl: [5.5] });
  expect(payload.kochzeit_min).toBe(70);
  expect(payload.karbonisierung_g_l).toBe(4.5);
  expect(payload.anstellhinweis).toBe("bei 9,5 Grad anstellen");
  expect(payload.yeast).toBe("3470 Wagner");
  expect(payload.original_gravity_plato).toBe(12.5);
});

test("zeigt den Brauzettel auf der Rezeptkarte", () => {
  const voll = recipe({
    malts: [{ name: "Pilsner Malz", kg: 250, maelzerei: "BM" }],
    hop_gaben: [
      { name: "Perle", gramm: 1800, zeitpunkt: "Kochbeginn", alpha_prozent: 6.5 },
    ],
    maischplan: [
      { schritt: "Einmaischen", temp_c: 61.5, dauer_min: 10 },
      { schritt: "Rast", temp_c: 72, dauer_min: 20 },
    ],
    wasser: { hauptguss_hl: 11, nachguss_hl: [5.5, 3] },
    yeast: "3470 Wagner",
    original_gravity_plato: 12.5,
    ibu: 24,
    color_ebc: 11,
    kochzeit_min: 70,
    karbonisierung_g_l: 4.5,
    anstellhinweis: "bei 9,5 Grad anstellen",
  });
  render(<Rezepte recipes={[voll]} onReload={() => {}} />);

  expect(screen.getByText(/Pilsner Malz 250 kg \(BM\)/)).toBeInTheDocument();
  expect(
    screen.getByText(/Hauptguss 11 hl · Nachgüsse 5.5 \+ 3 hl/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Einmaischen 61.5 °C \(10 min\) → Rast 72 °C \(20 min\)/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Perle 1800 g — Kochbeginn \(6.5 % α\)/),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      /Hefe: 3470 Wagner · 12.5 °P · 24 IBU · 11 EBC · Kochzeit 70 min · Karbonisierung 4.5 g\/l/,
    ),
  ).toBeInTheDocument();
  expect(screen.getByText(/Anstellen: bei 9,5 Grad anstellen/)).toBeInTheDocument();
});
