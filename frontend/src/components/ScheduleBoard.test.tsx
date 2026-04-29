import { render, screen } from "@testing-library/react";

import type { Sud, Tank } from "../api/types";
import { ScheduleBoard } from "./ScheduleBoard";

const TANK: Tank = {
  id: "tank-1",
  name: "F-30-1",
  cellar: "main",
  stage: "fermentation_closed",
  capacity_hl: 30,
  active: true,
};

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
  brew_date: "2026-04-20",
  status: "fermenting",
  notes: null,
  brewmaster: "seed",
  style_year_number: 17,
  occupancies: [
    {
      id: "occ-1",
      sud_id: "sud-1",
      tank_id: "tank-1",
      stage: "fermentation_closed",
      start_at: "2026-04-22T08:00:00Z",
      end_at: "2026-04-29T08:00:00Z",
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
    expect(screen.getByText(/Kellerbier Nr\. 17\/2026 · Gärtank/)).toBeInTheDocument();
  });
});
