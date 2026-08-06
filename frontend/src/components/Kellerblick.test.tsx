import { fireEvent, render, screen } from "@testing-library/react";

import type { Sud, Tank } from "../api/types";
import { Kellerblick } from "./Kellerblick";

const NOW = new Date();
const daysFromNow = (days: number) =>
  new Date(NOW.getTime() + days * 86_400_000).toISOString();

const STORAGE_TANK: Tank = {
  id: "tank-s1",
  name: "S-30-1",
  location_id: "loc-1",
  stage: "storage",
  capacity_hl: 30,
  active: true,
  locked: false,
};

const AUSSCHANK_TANK: Tank = {
  id: "tank-a50",
  name: "A-50",
  location_id: "loc-1",
  stage: "ausschank",
  capacity_hl: 50,
  active: true,
  locked: false,
};

const baseSud = (over: Partial<Sud>): Sud => ({
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
  brew_at: new Date().toISOString(),
  brew_date: new Date().toISOString().slice(0, 10),
  status: "storing",
  notes: null,
  brewmaster: "seed",
  style_year_number: 1,
  global_number: 210,
  volume_hl: 15,
  merged_into_sud_id: null,
  withdrawals: [],
  occupancies: [],
  ...over,
});

describe("Kellerblick", () => {
  it("shows the current tank card with remaining volume after withdrawals", () => {
    const sud = baseSud({
      occupancies: [
        {
          id: "occ-1",
          sud_id: "sud-1",
          tank_id: STORAGE_TANK.id,
          stage: "storage",
          start_at: daysFromNow(-3),
          end_at: daysFromNow(4),
          volume_hl: null,
        },
      ],
      withdrawals: [
        {
          id: "w-1",
          sud_id: "sud-1",
          tank_id: STORAGE_TANK.id,
          volume_hl: 5,
          at: daysFromNow(-1),
          kind: "keg_fill",
          notes: null,
        },
      ],
    });

    render(
      <Kellerblick tanks={[STORAGE_TANK, AUSSCHANK_TANK]} sude={[sud]} onChanged={() => {}} />,
    );

    expect(screen.getByText("S-30-1")).toBeInTheDocument();
    expect(screen.getByText(/noch 10 hl/)).toBeInTheDocument();
    expect(screen.getByText(/Tag 4 von 7/)).toBeInTheDocument();
    // Tap targets in fixed order: Umdrücken — Fass abfüllen — Ausgeschenkt.
    const actions = screen
      .getAllByRole("button")
      .map((b) => b.textContent)
      .filter((t) =>
        ["Umdrücken", "Fass abfüllen", "Ausgeschenkt"].includes(t ?? ""),
      );
    expect(actions).toEqual(["Umdrücken", "Fass abfüllen", "Ausgeschenkt"]);
    expect(screen.getByText(/Alter: Tag 4/)).toBeInTheDocument();
  });

  it("lists unplanned Sude with an Einplanen action and hides partners", () => {
    const unplanned = baseSud({ id: "sud-2", occupancies: [] });
    const partner = baseSud({
      id: "sud-3",
      style_year_number: 2,
      global_number: 211,
      merged_into_sud_id: "sud-2",
    });

    render(
      <Kellerblick
        tanks={[STORAGE_TANK]}
        sude={[unplanned, partner]}
        onChanged={() => {}}
      />,
    );

    // The unplanned lead folds the partner number into its label (Sorte n+m/Jahr)...
    expect(screen.getByText(/kellerbier 1\+2\//)).toBeInTheDocument();
    // ...and the global Sudnummer covers both brews of the pair.
    expect(screen.getByText("(Sud 210+211)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Einplanen" })).toBeInTheDocument();
    // ...and the partner gets no card of its own.
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });

  it("renders one card per tank for a multi-tank Ausschank split", () => {
    const split = baseSud({
      id: "sud-5",
      status: "in_ausschank",
      occupancies: [
        {
          id: "occ-a",
          sud_id: "sud-5",
          tank_id: AUSSCHANK_TANK.id,
          stage: "ausschank",
          start_at: daysFromNow(-1),
          end_at: null,
          volume_hl: 20,
        },
        {
          id: "occ-b",
          sud_id: "sud-5",
          tank_id: "tank-a80",
          stage: "ausschank",
          start_at: daysFromNow(-1),
          end_at: null,
          volume_hl: 10,
        },
      ],
    });
    const a80: Tank = {
      id: "tank-a80",
      name: "A-80",
      location_id: "loc-1",
      stage: "ausschank",
      capacity_hl: 80,
      active: true,
      locked: false,
    };

    render(
      <Kellerblick
        tanks={[AUSSCHANK_TANK, a80]}
        sude={[split]}
        onChanged={() => {}}
      />,
    );

    expect(screen.getByText("A-50")).toBeInTheDocument();
    expect(screen.getByText("A-80")).toBeInTheDocument();
    expect(screen.getByText(/noch 20 hl/)).toBeInTheDocument();
    expect(screen.getByText(/noch 10 hl/)).toBeInTheDocument();
    // Ausschank is no longer the end of the line — re-tanking stays possible.
    expect(screen.getAllByRole("button", { name: "Umdrücken" })).toHaveLength(2);
  });

  it("bündelt gemischte Ausschanktanks in einer Karte mit Tank-Aktionen", () => {
    const erster = baseSud({
      id: "sud-7",
      status: "in_ausschank",
      occupancies: [
        {
          id: "occ-k",
          sud_id: "sud-7",
          tank_id: AUSSCHANK_TANK.id,
          stage: "ausschank",
          start_at: daysFromNow(-1),
          end_at: null,
          volume_hl: 20,
        },
      ],
    });
    const zweiter = baseSud({
      id: "sud-8",
      status: "in_ausschank",
      style_year_number: 2,
      global_number: 211,
      occupancies: [
        {
          id: "occ-w",
          sud_id: "sud-8",
          tank_id: AUSSCHANK_TANK.id,
          stage: "ausschank",
          start_at: daysFromNow(-1),
          end_at: null,
          volume_hl: 10,
        },
      ],
    });

    render(
      <Kellerblick
        tanks={[AUSSCHANK_TANK]}
        sude={[erster, zweiter]}
        onChanged={() => {}}
      />,
    );

    // EIN Tank, EINE Karte — beide Biere als Zeilen, Buchungen am Tank.
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByText(/Zusammen noch 30 hl/)).toBeInTheDocument();
    // Vermischt ist vermischt: kein Umdrücken je Sud mehr (Stefan, 2026-08-06).
    expect(screen.queryByRole("button", { name: "Umdrücken" })).toBeNull();
    // Sichtbar ist nur die Alltagsaktion; der Rest steckt hinter „Mehr".
    expect(
      screen.getByRole("button", { name: "Ausgeschenkt" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Fass abfüllen" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Schwund" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Mehr" }));
    expect(
      screen.getByRole("button", { name: "Fass abfüllen" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Schwund" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Weniger" })).toBeInTheDocument();
  });

  it("keeps past-window Sude visible under Überfällig with a transfer action", () => {
    const overdue = baseSud({
      id: "sud-6",
      occupancies: [
        {
          id: "occ-c",
          sud_id: "sud-6",
          tank_id: STORAGE_TANK.id,
          stage: "storage",
          start_at: daysFromNow(-10),
          end_at: daysFromNow(-1),
          volume_hl: null,
        },
      ],
    });

    render(
      <Kellerblick
        tanks={[STORAGE_TANK, AUSSCHANK_TANK]}
        sude={[overdue]}
        onChanged={() => {}}
      />,
    );

    expect(screen.getByText("Überfällig")).toBeInTheDocument();
    expect(screen.getByText(/Bier steht noch im Tank/)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Umdrücken" }),
    ).toBeInTheDocument();
  });

  it("markiert Sude mit Prozess-Warnungen gelb und nennt den Grund", () => {
    const flagged = baseSud({
      status: "in_ausschank",
      warnings: ["Gärzeit evtl. zu kurz — Testfall."],
      occupancies: [
        {
          id: "occ-w",
          sud_id: "sud-1",
          tank_id: AUSSCHANK_TANK.id,
          stage: "ausschank",
          start_at: daysFromNow(-1),
          end_at: null,
          volume_hl: 15,
        },
      ],
    });

    render(
      <Kellerblick
        tanks={[AUSSCHANK_TANK]}
        sude={[flagged]}
        onChanged={() => {}}
      />,
    );

    expect(screen.getByText(/Gärzeit/)).toBeInTheDocument();
    const card = screen.getAllByRole("article")[0];
    expect(card.className).toContain("warn");
  });

  it("shows future-only Sude under Geplant without action buttons", () => {
    const planned = baseSud({
      id: "sud-4",
      occupancies: [
        {
          id: "occ-2",
          sud_id: "sud-4",
          tank_id: STORAGE_TANK.id,
          stage: "storage",
          start_at: daysFromNow(5),
          end_at: daysFromNow(12),
          volume_hl: null,
        },
      ],
    });

    render(<Kellerblick tanks={[STORAGE_TANK]} sude={[planned]} onChanged={() => {}} />);

    expect(screen.getByText("Geplant")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Umdrücken/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Umplanen" })).toBeInTheDocument();
  });
});

describe("Kellerblick (Rezept-Abweichungen)", () => {
  const runningOcc = {
    id: "occ-ov",
    sud_id: "sud-1",
    tank_id: STORAGE_TANK.id,
    stage: "storage" as const,
    start_at: daysFromNow(-2),
    end_at: daysFromNow(5),
    volume_hl: null,
  };

  it("markiert Sude mit Overrides als abweichend", () => {
    const deviating = baseSud({
      recipe_overrides: { fermentation_duration_days: 3 },
      occupancies: [runningOcc],
    });
    render(
      <Kellerblick tanks={[STORAGE_TANK]} sude={[deviating]} onChanged={() => {}} />,
    );
    expect(screen.getByText(/abweichende Rezeptzeiten/)).toBeInTheDocument();
  });

  it("zeigt keine Abweichung ohne Overrides", () => {
    const plain = baseSud({ recipe_overrides: null, occupancies: [runningOcc] });
    render(
      <Kellerblick tanks={[STORAGE_TANK]} sude={[plain]} onChanged={() => {}} />,
    );
    expect(screen.queryByText(/abweichende Rezeptzeiten/)).toBeNull();
  });
});
