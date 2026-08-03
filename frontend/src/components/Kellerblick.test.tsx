import { render, screen } from "@testing-library/react";

import type { Sud, Tank } from "../api/types";
import { Kellerblick } from "./Kellerblick";

const NOW = new Date();
const daysFromNow = (days: number) =>
  new Date(NOW.getTime() + days * 86_400_000).toISOString();

const STORAGE_TANK: Tank = {
  id: "tank-s1",
  name: "S-30-1",
  cellar: "main",
  stage: "storage",
  capacity_hl: 30,
  active: true,
};

const AUSSCHANK_TANK: Tank = {
  id: "tank-a50",
  name: "A-50",
  cellar: "main",
  stage: "ausschank",
  capacity_hl: 50,
  active: true,
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
  },
  brew_at: new Date().toISOString(),
  brew_date: new Date().toISOString().slice(0, 10),
  status: "storing",
  notes: null,
  brewmaster: "seed",
  style_year_number: 1,
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
      merged_into_sud_id: "sud-2",
    });

    render(
      <Kellerblick
        tanks={[STORAGE_TANK]}
        sude={[unplanned, partner]}
        onChanged={() => {}}
      />,
    );

    // The unplanned lead folds the partner number into its label...
    expect(screen.getByText(/Nr\. 1\+2\//)).toBeInTheDocument();
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
      cellar: "main",
      stage: "ausschank",
      capacity_hl: 80,
      active: true,
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
