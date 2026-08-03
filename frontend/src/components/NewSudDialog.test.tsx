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
  created_at: "2026-01-01T00:00:00Z",
  created_by: null,
  notes: null,
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
  created_at: "2026-01-01T00:00:00Z",
  created_by: null,
  notes: null,
};

const CLOSED_FERM_TANK: Tank = {
  id: "tank-closed",
  name: "F-30-1",
  location_id: "loc-1",
  stage: "fermentation_closed",
  capacity_hl: 30,
  active: true,
  locked: false,
};

const OPEN_FERM_TANK: Tank = {
  id: "tank-open",
  name: "F-OPEN-15",
  location_id: "loc-1",
  stage: "fermentation_open",
  capacity_hl: 15,
  active: true,
  locked: false,
};

const STORAGE_TANK: Tank = {
  id: "tank-storage",
  name: "S-30-1",
  location_id: "loc-1",
  stage: "storage",
  capacity_hl: 30,
  active: true,
  locked: false,
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

    const tankSelect = screen.getByLabelText("Gärtank (offen)") as HTMLSelectElement;
    const optionTexts = Array.from(tankSelect.options).map((o) => o.text);
    expect(optionTexts).toContain("F-OPEN-15 (15 hl)");
    expect(optionTexts).not.toContain("F-30-1 (30 hl)");
  });
});

describe("NewSudDialog (Phase 3)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("bietet nur die neueste Rezeptversion je Stil an", () => {
    const v2 = { ...KELLERBIER, id: "recipe-keller-v2", version: 2 };
    render(
      <NewSudDialog
        open
        recipes={[KELLERBIER, v2]}
        tanks={[CLOSED_FERM_TANK]}
        onClose={() => {}}
        onCreated={() => {}}
      />,
    );
    const select = screen.getByLabelText("Rezept") as HTMLSelectElement;
    const texts = Array.from(select.options).map((o) => o.text);
    expect(texts).toContain("Kellerbier (v2)");
    expect(texts).not.toContain("Kellerbier (v1)");
  });

  it("schickt Abweichungen als recipe_overrides mit", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: "sud-neu", warnings: [] }),
    });

    render(
      <NewSudDialog
        open
        recipes={[KELLERBIER]}
        tanks={[CLOSED_FERM_TANK]}
        onClose={() => {}}
        onCreated={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText("Rezept"), {
      target: { value: KELLERBIER.id },
    });
    // Ohne Einplanung — nur der Override zählt hier.
    fireEvent.click(screen.getByLabelText("Direkt einplanen (Gärtank + Startzeit)"));
    fireEvent.click(
      screen.getByLabelText("Abweichungen vom Rezept für diesen Sud"),
    );
    fireEvent.change(screen.getByLabelText("Gärung (Tage, Rezept: 7)"), {
      target: { value: "5" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Anlegen" }));

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [path, init] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/sude");
    const body = JSON.parse(init.body);
    expect(body.recipe_overrides).toEqual({ fermentation_duration_days: 5 });
  });
});

describe("NewSudDialog (Override-Hygiene)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("verwirft Overrides beim Rezeptwechsel", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: "sud-neu", warnings: [] }),
    });

    render(
      <NewSudDialog
        open
        recipes={[KELLERBIER, WEIZEN]}
        tanks={[CLOSED_FERM_TANK, OPEN_FERM_TANK]}
        onClose={() => {}}
        onCreated={() => {}}
      />,
    );
    // Weizen wählen, offene-Gärung-Override eintragen …
    fireEvent.change(screen.getByLabelText("Rezept"), {
      target: { value: WEIZEN.id },
    });
    fireEvent.click(
      screen.getByLabelText("Abweichungen vom Rezept für diesen Sud"),
    );
    fireEvent.change(screen.getByLabelText(/Offene Gärung \(Tage, Rezept: 4\)/), {
      target: { value: "2" },
    });
    // … dann auf Kellerbier wechseln: der versteckte Wert darf NICHT mit.
    fireEvent.change(screen.getByLabelText("Rezept"), {
      target: { value: KELLERBIER.id },
    });
    fireEvent.click(screen.getByLabelText("Direkt einplanen (Gärtank + Startzeit)"));
    fireEvent.click(screen.getByRole("button", { name: "Anlegen" }));

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse(init.body);
    expect(body.recipe_overrides).toBeUndefined();
  });
});
