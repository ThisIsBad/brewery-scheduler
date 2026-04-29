import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";

import type { Recipe, Tank } from "../api/types";
import { NewSudDialog } from "./NewSudDialog";

const KELLERBIER: Recipe = {
  id: "recipe-keller",
  beer_style: "kellerbier",
  version: 1,
  name: "Kellerbier",
  fermentation_duration_days: 7,
  open_fermentation_required: false,
  open_fermentation_duration_days: null,
  storage_duration_days: 21,
  max_storage_duration_days: 60,
};

const WEIZEN: Recipe = {
  id: "recipe-weizen",
  beer_style: "wheat",
  version: 1,
  name: "Weizen",
  fermentation_duration_days: 7,
  open_fermentation_required: true,
  open_fermentation_duration_days: 4,
  storage_duration_days: 14,
  max_storage_duration_days: 45,
};

const CLOSED_FERM_TANK: Tank = {
  id: "tank-closed",
  name: "F-30-1",
  cellar: "main",
  stage: "fermentation_closed",
  capacity_hl: 30,
  active: true,
};

const OPEN_FERM_TANK: Tank = {
  id: "tank-open",
  name: "F-OPEN-15",
  cellar: "main",
  stage: "fermentation_open",
  capacity_hl: 15,
  active: true,
};

const STORAGE_TANK: Tank = {
  id: "tank-storage",
  name: "S-30-1",
  cellar: "main",
  stage: "storage",
  capacity_hl: 30,
  active: true,
};

describe("NewSudDialog", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders nothing when closed", () => {
    const { container } = render(
      <NewSudDialog
        open={false}
        recipes={[KELLERBIER]}
        tanks={[CLOSED_FERM_TANK]}
        onClose={() => {}}
        onCreated={() => {}}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("limits the tank dropdown to closed fermentation tanks for non-wheat recipes", () => {
    render(
      <NewSudDialog
        open
        recipes={[KELLERBIER]}
        tanks={[CLOSED_FERM_TANK, OPEN_FERM_TANK, STORAGE_TANK]}
        onClose={() => {}}
        onCreated={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText("Rezept"), {
      target: { value: KELLERBIER.id },
    });

    const tankSelect = screen.getByLabelText("Gärtank") as HTMLSelectElement;
    const optionTexts = Array.from(tankSelect.options).map((o) => o.text);
    expect(optionTexts).toContain("F-30-1 (30 hl)");
    expect(optionTexts).not.toContain("F-OPEN-15 (15 hl)");
    expect(optionTexts).not.toContain("S-30-1 (30 hl)");
  });

  it("switches to the open fermentation tank when wheat is chosen", () => {
    render(
      <NewSudDialog
        open
        recipes={[KELLERBIER, WEIZEN]}
        tanks={[CLOSED_FERM_TANK, OPEN_FERM_TANK]}
        onClose={() => {}}
        onCreated={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText("Rezept"), {
      target: { value: WEIZEN.id },
    });

    const tankSelect = screen.getByLabelText("Offener Gärtank") as HTMLSelectElement;
    const optionTexts = Array.from(tankSelect.options).map((o) => o.text);
    expect(optionTexts).toContain("F-OPEN-15 (15 hl)");
    expect(optionTexts).not.toContain("F-30-1 (30 hl)");
  });
});
