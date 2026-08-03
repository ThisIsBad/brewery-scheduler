import { render, screen } from "@testing-library/react";

import type { Sud, Tank } from "../api/types";
import { ScheduleBoard } from "./ScheduleBoard";

const TANK: Tank = {
  id: "tank-1",
  name: "F-30-1",
  location_id: "loc-1",
  stage: "fermentation_closed",
  capacity_hl: 30,
  active: true,
  locked: false,
};

// Fixture dates are derived from "now" so the occupancy always falls inside
// the timeline's default visible window — hardcoded dates expire once the
// window (now-7d..now+21d) moves past them and the item is silently culled.
const NOW = new Date();
const daysFromNow = (days: number) =>
  new Date(NOW.getTime() + days * 24 * 60 * 60 * 1000);
const isoDate = (d: Date) => d.toISOString().slice(0, 10);

const BREW_DATE = isoDate(NOW);
const BREW_YEAR = NOW.getFullYear();

const SUD: Sud = {
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
  brew_at: NOW.toISOString(),
  brew_date: BREW_DATE,
  status: "fermenting",
  notes: null,
  brewmaster: "seed",
  style_year_number: 17,
  volume_hl: 15,
  merged_into_sud_id: null,
  withdrawals: [],
  occupancies: [
    {
      id: "occ-1",
      sud_id: "sud-1",
      tank_id: "tank-1",
      stage: "fermentation_closed",
      start_at: daysFromNow(-2).toISOString(),
      end_at: daysFromNow(5).toISOString(),
      volume_hl: null,
    },
  ],
};

describe("ScheduleBoard", () => {
  it("renders one row per tank with capacity in hl", () => {
    render(<ScheduleBoard tanks={[TANK]} sude={[SUD]} onMoveOccupancy={() => {}} />);
    expect(screen.getByText(/F-30-1/)).toBeInTheDocument();
    expect(screen.getByText(/30 hl/)).toBeInTheDocument();
  });

  it("renders the Sud-Nr in the block title", () => {
    render(<ScheduleBoard tanks={[TANK]} sude={[SUD]} onMoveOccupancy={() => {}} />);
    const expected = new RegExp(`Kellerbier Nr\\. 17/${BREW_YEAR} · Gärtank`);
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it("folds merged-batch partner numbers into the lead's block title", () => {
    const partner: Sud = {
      ...SUD,
      id: "sud-2",
      style_year_number: 18,
      merged_into_sud_id: SUD.id,
      occupancies: [],
    };
    render(
      <ScheduleBoard
        tanks={[TANK]}
        sude={[SUD, partner]}
        onMoveOccupancy={() => {}}
      />,
    );
    const expected = new RegExp(`Kellerbier Nr\\. 17\\+18/${BREW_YEAR} · Gärtank`);
    expect(screen.getByText(expected)).toBeInTheDocument();
  });
});
