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
  global_number: 285,
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
    // Die Aktionsleiste nennt die globale Sudnummer.
    expect(within(bar).getByText(/Sud 285/)).toBeInTheDocument();
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

describe("Zeitplan (Sudsicht)", () => {
  const zweiStationen: Sud = {
    ...sud,
    occupancies: [
      sud.occupancies[0],
      {
        id: "occ-2",
        sud_id: "sud-1",
        tank_id: F30B.id,
        stage: "fermentation_closed",
        start_at: daysFromNow(8),
        end_at: daysFromNow(15),
        volume_hl: null,
      },
    ],
  };

  it("Umschalter: Sudsicht zeigt eine Zeile je Charge mit Tanknamen als Blöcke", () => {
    render(
      <Zeitplan
        tanks={[F30, F30B]}
        sude={[zweiStationen]}
        onMoveOccupancy={() => {}}
        onResizeOccupancy={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Sude" }));
    // Zeilenlabel ist die Charge, die Blöcke tragen die Tanknamen der Kette.
    expect(screen.getByText(/kellerbier 1\/\d{4}/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "F-30-1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "F-30-2" })).toBeInTheDocument();

    // Auswahl + Aktionsleiste funktionieren wie in der Tanksicht.
    fireEvent.click(screen.getByRole("button", { name: "F-30-2" }));
    expect(
      screen.getByRole("toolbar", { name: "Sud verschieben" }),
    ).toBeInTheDocument();
  });

  it("Tanksicht: Auswahl hebt die Kette hervor und dimmt fremde Sude", () => {
    const anderer: Sud = {
      ...sud,
      id: "sud-9",
      style_year_number: 2,
      global_number: 286,
      occupancies: [
        {
          id: "occ-9",
          sud_id: "sud-9",
          tank_id: F30B.id,
          stage: "fermentation_closed",
          start_at: daysFromNow(2),
          end_at: daysFromNow(9),
          volume_hl: null,
        },
      ],
    };
    render(
      <Zeitplan
        tanks={[F30, F30B]}
        sude={[zweiStationen, anderer]}
        onMoveOccupancy={() => {}}
        onResizeOccupancy={() => {}}
      />,
    );

    fireEvent.click(screen.getAllByRole("button", { name: /kellerbier 1\/\d{4}/ })[0]);
    const bloecke = screen.getAllByRole("button", { name: /kellerbier/ });
    const klassen = bloecke.map((b) => b.className);
    // Die zweite Station derselben Charge trägt die Ketten-Markierung …
    expect(klassen.some((k) => k.includes("kette"))).toBe(true);
    // … und der fremde Sud tritt zurück.
    expect(klassen.some((k) => k.includes("fremd"))).toBe(true);
  });
});

describe("Zeitplan (Sudsicht-Sortierung)", () => {
  it("ordnet aufsteigend nach globaler Nummer; Paare zählen mit der niedrigeren", () => {
    // 290 startet FRÜHER, steht aber hinter dem 285er-Paar (285+286 < 290).
    const paarLead: Sud = {
      ...sud,
      id: "sud-p",
      global_number: 286,
      occupancies: [
        { ...sud.occupancies[0], id: "occ-p", sud_id: "sud-p", start_at: daysFromNow(5), end_at: daysFromNow(12) },
      ],
    };
    const paarPartner: Sud = {
      ...sud,
      id: "sud-q",
      style_year_number: 2,
      global_number: 285,
      merged_into_sud_id: "sud-p",
      occupancies: [],
    };
    const spaeterNummeriert: Sud = {
      ...sud,
      id: "sud-r",
      style_year_number: 3,
      global_number: 290,
      occupancies: [
        { ...sud.occupancies[0], id: "occ-r", sud_id: "sud-r", tank_id: F30B.id, start_at: daysFromNow(1), end_at: daysFromNow(4) },
      ],
    };

    const { container } = render(
      <Zeitplan
        tanks={[F30, F30B]}
        sude={[spaeterNummeriert, paarLead, paarPartner]}
        onMoveOccupancy={() => {}}
        onResizeOccupancy={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Sude" }));

    const labels = [...container.querySelectorAll(".zeitplan-tanklabel span")].map(
      (el) => el.textContent ?? "",
    );
    const posPaar = labels.findIndex((t) => t.includes("Sud 285+286"));
    const posSpaeter = labels.findIndex((t) => t.includes("Sud 290"));
    expect(posPaar).toBeGreaterThanOrEqual(0);
    expect(posSpaeter).toBeGreaterThanOrEqual(0);
    expect(posPaar).toBeLessThan(posSpaeter);
  });
});
