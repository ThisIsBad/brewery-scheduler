import { fireEvent, render, screen } from "@testing-library/react";

import type { Recipe, Sud } from "../api/types";
import { Einkaufsliste } from "./Einkaufsliste";

const isoIn = (days: number) =>
  new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);

const rezept = (over: Partial<Recipe>): Recipe => ({
  id: "r-1",
  beer_style: "Kellerbier Hell",
  version: 1,
  name: "Brudi",
  fermentation_duration_days: 7,
  open_fermentation_required: false,
  open_fermentation_duration_days: null,
  storage_duration_days: 21,
  max_storage_duration_days: 60,
  created_at: "2026-01-01T00:00:00Z",
  created_by: null,
  notes: null,
  malts: [
    { name: "Pilsner", kg: 250, maelzerei: "BM" },
    { name: "Cara Hell", kg: 25, maelzerei: "Weyermann" },
  ],
  hop_gaben: [
    { name: "Perle", gramm: 600, zeitpunkt: "Kochbeginn" },
    { name: "Citra", gramm: 400, zeitpunkt: "Whirlpool" },
  ],
  ...over,
});

const sudAm = (id: string, tag: string, recipeId = "r-1", nr = 1): Sud => ({
  id,
  recipe_id: recipeId,
  recipe: rezept({ id: recipeId }),
  brew_at: `${tag}T08:00:00Z`,
  brew_date: tag,
  status: "planned",
  notes: null,
  brewmaster: null,
  style_year_number: nr,
  global_number: 200 + nr,
  volume_hl: 15,
  merged_into_sud_id: null,
  withdrawals: [],
  occupancies: [],
});

test("summiert Malz und Hopfen über alle Sude im Zeitraum", () => {
  const weizenRezept = rezept({
    id: "r-2",
    beer_style: "Weizen",
    name: "Weizen Fritz",
    malts: [{ name: "Pilsner", kg: 58, maelzerei: "BM" }],
    hop_gaben: [{ name: "Fantasia", gramm: 1000, zeitpunkt: "nach 10 min" }],
  });
  const sude = [
    sudAm("s-1", isoIn(3)),
    sudAm("s-2", isoIn(10)),
    sudAm("s-3", isoIn(5), "r-2", 1),
    sudAm("s-4", isoIn(60), "r-1", 2), // außerhalb des Standardzeitraums
  ];

  render(<Einkaufsliste sude={sude} recipes={[rezept({}), weizenRezept]} />);

  expect(screen.getByText("Sude im Zeitraum (3)")).toBeInTheDocument();
  // Malz: Pilsner/BM aus drei Suden (250 + 250 + 58), Cara Hell aus zweien.
  expect(screen.getByText("558 kg")).toBeInTheDocument();
  expect(screen.getByText("50 kg")).toBeInTheDocument();
  // Hopfen: Perle 1200 g → 1,2 kg; Fantasia 1000 g → 1,0 kg; Citra 800 g.
  expect(screen.getByText("1,2 kg")).toBeInTheDocument();
  expect(screen.getByText("1,0 kg")).toBeInTheDocument();
  expect(screen.getByText("800 g")).toBeInTheDocument();
  // Malzsumme: 558 + 50 = 608 kg.
  expect(screen.getByText("608 kg")).toBeInTheDocument();
});

test("Von/Bis grenzen die Liste ein", () => {
  const sude = [sudAm("s-1", isoIn(3)), sudAm("s-2", isoIn(10), "r-1", 2)];
  render(<Einkaufsliste sude={sude} recipes={[rezept({})]} />);

  expect(screen.getByText("Sude im Zeitraum (2)")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Bis"), {
    target: { value: isoIn(5) },
  });
  expect(screen.getByText("Sude im Zeitraum (1)")).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Von"), {
    target: { value: isoIn(4) },
  });
  expect(screen.getByText("Sude im Zeitraum (0)")).toBeInTheDocument();
  expect(
    screen.getByText(/Keine Sude mit Sudtag in diesem Zeitraum/),
  ).toBeInTheDocument();
});
