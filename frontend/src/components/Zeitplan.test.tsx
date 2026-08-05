import { fireEvent, render, screen, within } from "@testing-library/react";
import { vi } from "vitest";

import type { Sud, Tank } from "../api/types";
import { Zeitplan } from "./Zeitplan";

const NOW = new Date();
const daysFromNow = (days: number) =>
  new Date(NOW.getTime() + days * 86_400_000).toISOString();

const F30: Tank = {
  id: "tank-f30",
  name: "F-30-1",
  location_id: "loc-1",
  stage: "fermentation_closed",
  capacity_hl: 30,
  active: true,
  locked: false,
};

const F30B: Tank = {
  id: "tank-f30b",
  name: "F-30-2",
  location_id: "loc-1",
  stage: "fermentation_closed",
  capacity_hl: 30,
  active: true,
  locked: false,
};

const sud: Sud = {
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
  brew_at: daysFromNow(-1),
  brew_date: daysFromNow(-1).slice(0, 10),
  status: "fermenting",
  notes: null,
  brewmaster: null,
  style_year_number: 1,
  volume_hl: 15,
  merged_into_sud_id: null,
  occupancies: [
    {
      id: "occ-1",
      sud_id: "sud-1",
      tank_id: F30.id,
      stage: "fermentation_closed",
      start_at: daysFromNow(1),
      end_at: daysFromNow(8),
      volume_hl: null,
    },
  ],
  withdrawals: [],
};

describe("Zeitplan (Bierfarbe)", () => {
  it("färbt den Sud-Block mit der Rezeptfarbe und wählt lesbaren Text", () => {
    const gefaerbt: Sud = {
      ...sud,
      recipe: { ...sud.recipe, farbe: "#c0392b" },
    };
    render(
      <Zeitplan tanks={[F30]} sude={[gefaerbt]} onMoveOccupancy={() => {}} onResizeOccupancy={() => {}} />,
    );
    const block = screen.getByRole("button", { name: /kellerbier 1\// });
    expect(block.style.background).toBe("rgb(192, 57, 43)");
    expect(block.style.color).toBe("rgb(255, 255, 255)");
  });
});

describe("Zeitplan (Touch-Timeline)", () => {
  it("rendert Tankzeilen und Sud-Blöcke", () => {
    render(
      <Zeitplan tanks={[F30, F30B]} sude={[sud]} onMoveOccupancy={() => {}} onResizeOccupancy={() => {}} />,
    );
    expect(screen.getByText("F-30-1")).toBeInTheDocument();
    expect(screen.getByText("F-30-2")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /kellerbier 1\/\d{4}/ }),
    ).toBeInTheDocument();
  });

  it("Tippen wählt aus, +1 Tag verschiebt den Start um einen Tag", () => {
    const onMove = vi.fn();
    render(<Zeitplan tanks={[F30, F30B]} sude={[sud]} onMoveOccupancy={onMove} onResizeOccupancy={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /kellerbier 1\/\d{4}/ }));
    const bar = screen.getByRole("toolbar", { name: "Sud verschieben" });
    fireEvent.click(within(bar).getByRole("button", { name: "Start +1 Tag" }));

    expect(onMove).toHaveBeenCalledWith(
      "sud-1",
      "occ-1",
      F30.id,
      new Date(sud.occupancies[0].start_at).getTime() + 86_400_000,
    );
  });

  it("Tankwechsel über das Dropdown behält den Start bei", () => {
    const onMove = vi.fn();
    render(<Zeitplan tanks={[F30, F30B]} sude={[sud]} onMoveOccupancy={onMove} onResizeOccupancy={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: /kellerbier 1\/\d{4}/ }));
    fireEvent.change(screen.getByLabelText("Tank wechseln"), {
      target: { value: F30B.id },
    });

    expect(onMove).toHaveBeenCalledWith(
      "sud-1",
      "occ-1",
      F30B.id,
      new Date(sud.occupancies[0].start_at).getTime(),
    );
  });

  it("Dauer +7 verlängert nur die Dauer, der Start bleibt", () => {
    const onResize = vi.fn();
    render(
      <Zeitplan
        tanks={[F30, F30B]}
        sude={[sud]}
        onMoveOccupancy={() => {}}
        onResizeOccupancy={onResize}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /kellerbier 1\/\d{4}/ }));
    const bar = screen.getByRole("toolbar", { name: "Sud verschieben" });
    // Info zeigt von–bis mit Dauer (7 Tage im Fixture).
    expect(within(bar).getByText(/\(7 Tage\)/)).toBeInTheDocument();
    fireEvent.click(within(bar).getByRole("button", { name: "Dauer +7 Tage" }));

    expect(onResize).toHaveBeenCalledWith(
      "sud-1",
      "occ-1",
      new Date(sud.occupancies[0].end_at!).getTime() + 7 * 86_400_000,
    );
    // Kürzen unter den Start hinaus ist gesperrt (7 Tage Dauer → −7 ergäbe 0).
    expect(
      within(bar).getByRole("button", { name: "Dauer −7 Tage" }),
    ).toBeDisabled();
  });

  it("markiert Sude mit Warnungen auch im Zeitplan", () => {
    const warned = { ...sud, warnings: ["Gärzeit evtl. zu kurz — Test."] };
    render(<Zeitplan tanks={[F30]} sude={[warned]} onMoveOccupancy={() => {}} onResizeOccupancy={() => {}} />);
    const block = screen.getByRole("button", { name: /kellerbier 1\/\d{4}/ });
    expect(block.className).toContain("warn");
  });
});

describe("Zeitplan (Auswahl überlebt Moves)", () => {
  it("findet die Auswahl nach ID-Wechsel per Stufe + Start wieder", () => {
    const onMove = vi.fn();
    const { rerender } = render(
      <Zeitplan tanks={[F30, F30B]} sude={[sud]} onMoveOccupancy={onMove} onResizeOccupancy={() => {}} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /kellerbier 1\/\d{4}/ }));
    expect(
      screen.getByRole("toolbar", { name: "Sud verschieben" }),
    ).toBeInTheDocument();

    // Der Server ersetzt die Occupancy-Zeile: neue ID, Start +1 Tag.
    const moved: Sud = {
      ...sud,
      occupancies: [
        {
          ...sud.occupancies[0],
          id: "occ-NEU",
          start_at: daysFromNow(2),
          end_at: daysFromNow(9),
        },
      ],
    };
    rerender(
      <Zeitplan tanks={[F30, F30B]} sude={[moved]} onMoveOccupancy={onMove} onResizeOccupancy={() => {}} />,
    );

    const bar = screen.getByRole("toolbar", { name: "Sud verschieben" });
    fireEvent.click(within(bar).getByRole("button", { name: "Start +1 Tag" }));
    expect(onMove).toHaveBeenLastCalledWith(
      "sud-1",
      "occ-NEU",
      F30.id,
      new Date(moved.occupancies[0].start_at).getTime() + 86_400_000,
    );
  });
});
