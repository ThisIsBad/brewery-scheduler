import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { api } from "../api/client";
import type { Sud, Tank, Verlaufseintrag } from "../api/types";
import { Verlauf } from "./Verlauf";

const SUD = {
  id: "sud-1",
  global_number: 285,
  style_year_number: 17,
  brew_date: "2026-07-01",
  merged_into_sud_id: null,
  recipe: { beer_style: "Kellerbier Hell", name: "Brudi" },
} as unknown as Sud;

const TANKS = [{ id: "tank-1", name: "Kitzmann vorne" }] as unknown as Tank[];

const eintrag = (over: Partial<Verlaufseintrag>): Verlaufseintrag => ({
  id: "e-1",
  at: "2026-08-07T09:30:00+00:00",
  actor: "stefan",
  action: "update",
  entity: "tanks",
  entity_id: "tank-1",
  sud_id: null,
  changes: {},
  ...over,
});

beforeEach(() => {
  vi.restoreAllMocks();
});

test("nennt Person, Bereich und die Änderung im Klartext", async () => {
  vi.spyOn(api, "listVerlauf").mockResolvedValue([
    eintrag({ changes: { capacity_hl: { alt: 80, neu: 90 } } }),
  ]);

  render(<Verlauf sude={[SUD]} tanks={TANKS} />);

  await waitFor(() => expect(screen.getByText(/stefan/)).toBeInTheDocument());
  expect(screen.getByText(/Tank geändert/)).toBeInTheDocument();
  expect(screen.getByText("Größe: 80 → 90")).toBeInTheDocument();
});

test("zeigt Dezimalzahlen deutsch und leere Werte als Strich", async () => {
  vi.spyOn(api, "listVerlauf").mockResolvedValue([
    eintrag({ changes: { verbrauch_hl_pro_woche: { alt: null, neu: 51.8 } } }),
  ]);

  render(<Verlauf sude={[SUD]} tanks={TANKS} />);

  await waitFor(() =>
    expect(screen.getByText("Ø-Ausschank: — → 51,8")).toBeInTheDocument(),
  );
});

test("nennt Tanks beim Namen und verschweigt sonstige Kennungen", async () => {
  vi.spyOn(api, "listVerlauf").mockResolvedValue([
    eintrag({
      entity: "tank_occupancy",
      changes: {
        tank_id: { alt: "0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0", neu: "tank-1" },
        recipe_id: { alt: null, neu: "8a7b6c5d-4e3f-2109-8877-665544332211" },
      },
    }),
  ]);

  render(<Verlauf sude={[SUD]} tanks={TANKS} />);

  await waitFor(() =>
    expect(screen.getByText(/Tankbelegung geändert/)).toBeInTheDocument(),
  );
  // Unbekannter Tank bleibt „…", der bekannte bekommt seinen Namen.
  expect(screen.getByText("Tank: … → Kitzmann vorne")).toBeInTheDocument();
  expect(screen.getByText("recipe_id: — → …")).toBeInTheDocument();
});

test("nennt den Sud, weil keine Karte mehr den Zusammenhang liefert", async () => {
  vi.spyOn(api, "listVerlauf").mockResolvedValue([
    eintrag({
      entity: "withdrawals",
      sud_id: "sud-1",
      action: "create",
      changes: { kind: "ausschank", volume_hl: 1.5 },
    }),
  ]);

  render(<Verlauf sude={[SUD]} tanks={TANKS} />);

  await waitFor(() =>
    expect(
      screen.getByText(/Abgang angelegt — Kellerbier Hell 17\/2026/),
    ).toBeInTheDocument(),
  );
  expect(screen.getByText("Menge: 1,5")).toBeInTheDocument();
});

test("gruppiert nach Tagen, damit „wer war gestern dran\" beantwortbar ist", async () => {
  vi.spyOn(api, "listVerlauf").mockResolvedValue([
    eintrag({ id: "e-1", at: "2026-08-07T09:30:00+00:00" }),
    eintrag({ id: "e-2", at: "2026-08-07T08:00:00+00:00" }),
    eintrag({ id: "e-3", at: "2026-08-06T17:00:00+00:00", actor: "vincenz" }),
  ]);

  render(<Verlauf sude={[SUD]} tanks={TANKS} />);

  await waitFor(() =>
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(2),
  );
  const tage = screen
    .getAllByRole("heading", { level: 3 })
    .map((h) => h.textContent);
  expect(tage[0]).toMatch(/07\.08\.2026/);
  expect(tage[1]).toMatch(/06\.08\.2026/);
});

test("sagt es, wenn noch nichts aufgezeichnet wurde", async () => {
  vi.spyOn(api, "listVerlauf").mockResolvedValue([]);

  render(<Verlauf sude={[SUD]} tanks={TANKS} />);

  await waitFor(() =>
    expect(
      screen.getByText("Noch keine Änderungen aufgezeichnet."),
    ).toBeInTheDocument(),
  );
});
