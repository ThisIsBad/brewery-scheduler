import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";

import type { Occupancy, Sud, Tank } from "../api/types";
import { ReplanDialog } from "./ReplanDialog";
import { ScheduleDialog } from "./ScheduleDialog";
import { TankWithdrawDialog } from "./TankWithdrawDialog";
import { TransferDialog } from "./TransferDialog";
import { WithdrawDialog } from "./WithdrawDialog";

vi.mock("../api/client", () => ({
  api: {
    transferSud: vi.fn(),
    withdraw: vi.fn(),
    tankWithdraw: vi.fn(),
    updateSchedule: vi.fn(),
  },
}));

import { api } from "../api/client";

const mocked = api as unknown as {
  transferSud: ReturnType<typeof vi.fn>;
  withdraw: ReturnType<typeof vi.fn>;
  tankWithdraw: ReturnType<typeof vi.fn>;
  updateSchedule: ReturnType<typeof vi.fn>;
};

const STORAGE_TANK: Tank = {
  id: "tank-s1",
  name: "S-30-1",
  location_id: "loc-1",
  stage: "storage",
  capacity_hl: 30,
  active: true,
  locked: false,
};

const A100: Tank = {
  id: "tank-a100",
  name: "A-100",
  location_id: "loc-1",
  stage: "ausschank",
  capacity_hl: 100,
  active: true,
  locked: false,
};

const A80: Tank = {
  id: "tank-a80",
  name: "A-80",
  location_id: "loc-1",
  stage: "ausschank",
  capacity_hl: 80,
  active: true,
  locked: false,
};

const F30: Tank = {
  id: "tank-f30",
  name: "F-30-1",
  location_id: "loc-1",
  stage: "fermentation_closed",
  capacity_hl: 30,
  active: true,
  locked: false,
};

const F15: Tank = {
  id: "tank-f15",
  name: "F-15-1",
  location_id: "loc-1",
  stage: "fermentation_closed",
  capacity_hl: 15,
  active: true,
  locked: false,
};

const sud = (over: Partial<Sud>): Sud => ({
  id: "sud-1",
  recipe_id: "recipe-1",
  recipe: {
    id: "recipe-1",
    beer_style: "festbier",
    version: 1,
    name: "Festbier",
    fermentation_duration_days: 8,
    open_fermentation_required: false,
    open_fermentation_duration_days: null,
    storage_duration_days: 28,
    max_storage_duration_days: 70,
    created_at: "2026-01-01T00:00:00Z",
    created_by: null,
    notes: null,
  },
  brew_at: "2026-08-01T09:00:00Z",
  brew_date: "2026-08-01",
  status: "storing",
  notes: null,
  brewmaster: null,
  style_year_number: 1,
  global_number: 210,
  volume_hl: 15,
  merged_into_sud_id: null,
  withdrawals: [],
  occupancies: [],
  ...over,
});

const storageOcc: Occupancy = {
  id: "occ-1",
  sud_id: "sud-1",
  tank_id: STORAGE_TANK.id,
  stage: "storage",
  start_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
  end_at: new Date(Date.now() + 4 * 86_400_000).toISOString(),
  volume_hl: null,
};

beforeEach(() => {
  mocked.transferSud.mockReset().mockResolvedValue(sud({}));
  mocked.withdraw.mockReset().mockResolvedValue(sud({}));
  mocked.tankWithdraw.mockReset().mockResolvedValue([]);
  mocked.updateSchedule.mockReset().mockResolvedValue(sud({}));
});

describe("TankWithdrawDialog (Blending)", () => {
  const occA: Occupancy = {
    id: "occ-ta",
    sud_id: "sud-1",
    tank_id: A100.id,
    stage: "ausschank",
    start_at: new Date(Date.now() - 86_400_000).toISOString(),
    end_at: null,
    volume_hl: 20,
  };
  const occB: Occupancy = {
    id: "occ-tb",
    sud_id: "sud-2",
    tank_id: A100.id,
    stage: "ausschank",
    start_at: new Date(Date.now() - 86_400_000).toISOString(),
    end_at: null,
    volume_hl: 10,
  };

  it("bucht am Tank, zeigt die Verteilung und meldet alle Sude zurück", async () => {
    const erster = sud({ id: "sud-1", occupancies: [occA] });
    const zweiter = sud({ id: "sud-2", style_year_number: 2, global_number: 211, occupancies: [occB] });
    const onDone = vi.fn();
    mocked.tankWithdraw.mockResolvedValue([erster, zweiter]);

    render(
      <TankWithdrawDialog
        tank={A100}
        entries={[
          { sud: erster, occ: occA },
          { sud: zweiter, occ: occB },
        ]}
        sude={[erster, zweiter]}
        kind="ausschank"
        onClose={() => {}}
        onDone={onDone}
      />,
    );

    expect(screen.getByText(/zusammen 30 hl/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Menge (hl)"), {
      target: { value: "9" },
    });
    // Vorschau der proportionalen Verteilung (2:1).
    expect(screen.getByText(/Verteilt sich/)).toBeInTheDocument();
    expect(screen.getByText(/~6 hl/)).toBeInTheDocument();
    expect(screen.getByText(/~3 hl/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Eintragen" }));
    await waitFor(() => expect(mocked.tankWithdraw).toHaveBeenCalledOnce());
    const [tankId, payload] = mocked.tankWithdraw.mock.calls[0];
    expect(tankId).toBe(A100.id);
    expect(payload.volume_hl).toBe(9);
    expect(payload.kind).toBe("ausschank");
    await waitFor(() => expect(onDone).toHaveBeenCalledWith([erster, zweiter]));
  });

  it("rechnet Fass-Stückzahlen am Tank in hl um und schickt kegs", async () => {
    const erster = sud({ id: "sud-1", occupancies: [occA] });
    const onDone = vi.fn();
    mocked.tankWithdraw.mockResolvedValue([erster]);
    render(
      <TankWithdrawDialog
        tank={A100}
        entries={[{ sud: erster, occ: occA }]}
        sude={[erster]}
        kind="keg_fill"
        onClose={() => {}}
        onDone={onDone}
      />,
    );

    fireEvent.change(screen.getByLabelText("Fässer 50 l (Stück)"), {
      target: { value: "4" },
    });
    fireEvent.change(screen.getByLabelText("Fässer 20 l (Stück)"), {
      target: { value: "3" },
    });
    expect(screen.getByText(/Ergibt 2.6 hl/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Abfüllen" }));
    await waitFor(() => expect(mocked.tankWithdraw).toHaveBeenCalledOnce());
    const [, payload] = mocked.tankWithdraw.mock.calls[0];
    expect(payload.kegs).toEqual([
      { size_l: 20, count: 3 },
      { size_l: 50, count: 4 },
    ]);
    expect(payload.volume_hl).toBeUndefined();
    expect(payload.kind).toBe("keg_fill");
  });

  it("sperrt Buchungen über dem Tankinhalt", () => {
    const erster = sud({ id: "sud-1", occupancies: [occA] });
    render(
      <TankWithdrawDialog
        tank={A100}
        entries={[{ sud: erster, occ: occA }]}
        sude={[erster]}
        kind="schwund"
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    fireEvent.change(screen.getByLabelText("Menge (hl)"), {
      target: { value: "25" },
    });
    expect(screen.getByText(/Nur 20 hl im Tank/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ausbuchen" })).toBeDisabled();
    expect(mocked.tankWithdraw).not.toHaveBeenCalled();
  });
});

describe("TransferDialog (Ausschank split)", () => {
  it("splits volumes across tanks and sends them once the sum matches", async () => {
    const lead = sud({ occupancies: [storageOcc] });
    const partner = sud({
      id: "sud-2",
      style_year_number: 2,
      global_number: 211,
      merged_into_sud_id: "sud-1",
    });

    render(
      <TransferDialog
        sud={lead}
        occupancy={storageOcc}
        tanks={[A100, A80, STORAGE_TANK]}
        sude={[lead, partner]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    // 30 hl combined: A-100 as target, split, 20 in there, 10 into A-80.
    fireEvent.change(screen.getByLabelText("Zieltank"), {
      target: { value: A100.id },
    });
    fireEvent.click(screen.getByRole("button", { name: "+ Tank aufteilen" }));
    fireEvent.change(screen.getByLabelText("Volumen 1 (hl)"), {
      target: { value: "20" },
    });
    fireEvent.change(screen.getByLabelText("Zieltank 2"), {
      target: { value: A80.id },
    });
    fireEvent.change(screen.getByLabelText("Volumen 2 (hl)"), {
      target: { value: "10" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Umdrücken" }));

    await waitFor(() => expect(mocked.transferSud).toHaveBeenCalledOnce());
    const [sudId, payload] = mocked.transferSud.mock.calls[0];
    expect(sudId).toBe("sud-1");
    expect(payload.allocations).toEqual([
      { tank_id: A100.id, volume_hl: 20 },
      { tank_id: A80.id, volume_hl: 10 },
    ]);
  });

  it("blocks submission while the split does not sum to the batch", () => {
    const lead = sud({ occupancies: [storageOcc] });
    render(
      <TransferDialog
        sud={lead}
        occupancy={storageOcc}
        tanks={[A100, A80]}
        sude={[lead]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    // 15 hl batch, but only 9 + 3 = 12 hl distributed.
    fireEvent.change(screen.getByLabelText("Zieltank"), {
      target: { value: A100.id },
    });
    fireEvent.click(screen.getByRole("button", { name: "+ Tank aufteilen" }));
    fireEvent.change(screen.getByLabelText("Volumen 1 (hl)"), {
      target: { value: "9" },
    });
    fireEvent.change(screen.getByLabelText("Zieltank 2"), {
      target: { value: A80.id },
    });
    fireEvent.change(screen.getByLabelText("Volumen 2 (hl)"), {
      target: { value: "3" },
    });

    expect(screen.getByRole("button", { name: "Umdrücken" })).toBeDisabled();
    expect(mocked.transferSud).not.toHaveBeenCalled();
  });
});

describe("TransferDialog (sortenreine Ausschanktanks)", () => {
  it("bietet Ausschanktanks mit fremder Sorte nicht an", () => {
    const lead = sud({ occupancies: [storageOcc] }); // Festbier
    const fremd = sud({
      id: "sud-9",
      recipe: { ...lead.recipe, id: "recipe-2", beer_style: "Weizen", name: "Weizen" },
      status: "in_ausschank",
      occupancies: [
        {
          id: "occ-fremd",
          sud_id: "sud-9",
          tank_id: A100.id,
          stage: "ausschank",
          start_at: new Date(Date.now() - 86_400_000).toISOString(),
          end_at: null,
          volume_hl: 15,
        },
      ],
    });

    render(
      <TransferDialog
        sud={lead}
        occupancy={storageOcc}
        tanks={[STORAGE_TANK, A100, A80]}
        sude={[lead, fremd]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    const options = within(
      screen.getByLabelText("Zieltank"),
    ).getAllByRole("option");
    const names = options.map((o) => o.textContent ?? "");
    // A-100 hält Weizen — für Festbier nicht wählbar; das leere A-80 schon.
    expect(names.some((n) => n.includes("A-100"))).toBe(false);
    expect(names.some((n) => n.includes("A-80"))).toBe(true);
  });

  it("sieht auch aufgeteilte und erst geplante Fremd-Belegungen", () => {
    const lead = sud({ occupancies: [storageOcc] }); // Festbier
    // Weizen liegt aufgeteilt in A-100 UND A-80 (zwei gleichzeitige
    // Belegungen) — beide Tanks sind fremd belegt.
    const gesplittet = sud({
      id: "sud-9",
      recipe: { ...lead.recipe, id: "recipe-2", beer_style: "Weizen", name: "Weizen" },
      status: "in_ausschank",
      occupancies: [
        {
          id: "occ-f1",
          sud_id: "sud-9",
          tank_id: A100.id,
          stage: "ausschank",
          start_at: new Date(Date.now() - 86_400_000).toISOString(),
          end_at: null,
          volume_hl: 8,
        },
        {
          id: "occ-f2",
          sud_id: "sud-9",
          tank_id: A80.id,
          stage: "ausschank",
          start_at: new Date(Date.now() - 86_400_000).toISOString(),
          end_at: null,
          volume_hl: 7,
        },
      ],
    });
    // Und in A-50 ist ab morgen fremdes Bier GEPLANT — das offene
    // Umdrück-Fenster würde damit kollidieren.
    const a50: Tank = {
      id: "tank-a50x",
      name: "A-50",
      location_id: "loc-1",
      stage: "ausschank",
      capacity_hl: 50,
      active: true,
      locked: false,
    };
    const geplant = sud({
      id: "sud-10",
      recipe: { ...lead.recipe, id: "recipe-2", beer_style: "Weizen", name: "Weizen" },
      occupancies: [
        {
          id: "occ-f3",
          sud_id: "sud-10",
          tank_id: a50.id,
          stage: "ausschank",
          start_at: new Date(Date.now() + 86_400_000).toISOString(),
          end_at: null,
          volume_hl: 15,
        },
      ],
    });

    render(
      <TransferDialog
        sud={lead}
        occupancy={storageOcc}
        tanks={[STORAGE_TANK, A100, A80, a50]}
        sude={[lead, gesplittet, geplant]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    const names = within(screen.getByLabelText("Zieltank"))
      .getAllByRole("option")
      .map((o) => o.textContent ?? "");
    expect(names.some((n) => n.includes("A-100"))).toBe(false);
    expect(names.some((n) => n.includes("A-80"))).toBe(false);
    expect(names.some((n) => n.includes("A-50"))).toBe(false);
  });
});

describe("TransferDialog (split at any stage)", () => {
  const S10A: Tank = {
    id: "tank-s10a",
    name: "S2-10-1",
    location_id: "loc-2",
    stage: "storage",
    capacity_hl: 10,
    active: true,
    locked: false,
  };
  const S10B: Tank = {
    id: "tank-s10b",
    name: "S2-10-2",
    location_id: "loc-2",
    stage: "storage",
    capacity_hl: 10,
    active: true,
    locked: false,
  };

  it("splits into two storage tanks and flags a share over capacity", async () => {
    const lead = sud({ occupancies: [storageOcc] });
    render(
      <TransferDialog
        sud={lead}
        occupancy={storageOcc}
        tanks={[STORAGE_TANK, S10A, S10B]}
        sude={[lead]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    // 15 hl into a 10-hl tank: blocked, with the hint to split further.
    fireEvent.change(screen.getByLabelText("Zieltank"), {
      target: { value: S10A.id },
    });
    expect(screen.getByText(/fasst nur 10 hl/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Umdrücken" })).toBeDisabled();

    // 8/7 across the two small tanks works and sends explicit shares.
    fireEvent.click(screen.getByRole("button", { name: "+ Tank aufteilen" }));
    fireEvent.change(screen.getByLabelText("Volumen 1 (hl)"), {
      target: { value: "8" },
    });
    fireEvent.change(screen.getByLabelText("Zieltank 2"), {
      target: { value: S10B.id },
    });
    fireEvent.change(screen.getByLabelText("Volumen 2 (hl)"), {
      target: { value: "7" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Umdrücken" }));

    await waitFor(() => expect(mocked.transferSud).toHaveBeenCalledOnce());
    const [, payload] = mocked.transferSud.mock.calls[0];
    expect(payload.from_tank_id).toBe(STORAGE_TANK.id);
    expect(payload.allocations).toEqual([
      { tank_id: S10A.id, volume_hl: 8 },
      { tank_id: S10B.id, volume_hl: 7 },
    ]);
  });

  it("moves only the tapped tank's share of a split batch", async () => {
    // The batch was split earlier; this occupancy holds an 8-hl share of
    // the 15-hl Sud. The dialog must offer the share, not the batch.
    const shareOcc: Occupancy = { ...storageOcc, volume_hl: 8 };
    const lead = sud({ occupancies: [shareOcc] });
    render(
      <TransferDialog
        sud={lead}
        occupancy={shareOcc}
        tanks={[STORAGE_TANK, S10A]}
        sude={[lead]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    expect(screen.getByText(/8 hl aus S-30-1/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Zieltank"), {
      target: { value: S10A.id },
    });
    fireEvent.click(screen.getByRole("button", { name: "Umdrücken" }));

    await waitFor(() => expect(mocked.transferSud).toHaveBeenCalledOnce());
    const [, payload] = mocked.transferSud.mock.calls[0];
    expect(payload.from_tank_id).toBe(STORAGE_TANK.id);
    expect(payload.allocations).toEqual([{ tank_id: S10A.id }]);
  });
});

describe("TransferDialog (remaining volume)", () => {
  it("distributes the remaining volume, not the brewed volume", () => {
    const lead = sud({
      occupancies: [storageOcc],
      withdrawals: [
        {
          id: "w-1",
          sud_id: "sud-1",
          tank_id: STORAGE_TANK.id,
          volume_hl: 2,
          at: new Date().toISOString(),
          kind: "keg_fill",
          notes: null,
        },
      ],
    });

    render(
      <TransferDialog
        sud={lead}
        occupancy={storageOcc}
        tanks={[A100]}
        sude={[lead]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    // 15 hl brewed − 2 hl in kegs = 13 hl to distribute.
    fireEvent.change(screen.getByLabelText("Zieltank"), {
      target: { value: A100.id },
    });
    expect(screen.getByText(/von 13 hl/)).toBeInTheDocument();
  });
});

describe("TransferDialog (free target choice)", () => {
  it("offers any tank and sends a plain single-tank move backward", async () => {
    const lead = sud({ occupancies: [storageOcc] });
    render(
      <TransferDialog
        sud={lead}
        occupancy={storageOcc}
        tanks={[F15, STORAGE_TANK, A100]}
        sude={[lead]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    // Storage → closed fermenter: unusual direction, but offered.
    fireEvent.change(screen.getByLabelText("Zieltank"), {
      target: { value: F15.id },
    });
    fireEvent.click(screen.getByRole("button", { name: "Umdrücken" }));

    await waitFor(() => expect(mocked.transferSud).toHaveBeenCalledOnce());
    const [, payload] = mocked.transferSud.mock.calls[0];
    expect(payload.allocations).toEqual([{ tank_id: F15.id }]);
  });
});

describe("WithdrawDialog", () => {
  it("sends the withdrawal and caps it at the remaining volume", async () => {
    const lead = sud({ occupancies: [storageOcc] });
    render(
      <WithdrawDialog
        sud={lead}
        occupancy={storageOcc}
        tanks={[STORAGE_TANK]}
        sude={[lead]}
        kind="ausschank"
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    const input = screen.getByLabelText("Menge (hl)");
    fireEvent.change(input, { target: { value: "20" } });
    expect(screen.getByRole("button", { name: "Eintragen" })).toBeDisabled();

    fireEvent.change(input, { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Eintragen" }));

    await waitFor(() => expect(mocked.withdraw).toHaveBeenCalledOnce());
    const [, payload] = mocked.withdraw.mock.calls[0];
    expect(payload.tank_id).toBe(STORAGE_TANK.id);
    expect(payload.volume_hl).toBe(5);
    expect(payload.kind).toBe("ausschank");
    expect(typeof payload.at).toBe("string");
  });
});

describe("ScheduleDialog", () => {
  it("offers only fermenters that fit the combined merged-batch volume", async () => {
    const lead = sud({ id: "sud-1", occupancies: [] });
    const partner = sud({
      id: "sud-2",
      style_year_number: 2,
      global_number: 211,
      merged_into_sud_id: "sud-1",
    });

    render(
      <ScheduleDialog
        sud={lead}
        tanks={[F30, F15]}
        sude={[lead, partner]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    const select = screen.getByLabelText("Gärtank") as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.text);
    expect(options.join(" ")).toContain("F-30-1");
    expect(options.join(" ")).not.toContain("F-15-1");

    fireEvent.change(select, { target: { value: F30.id } });
    fireEvent.click(screen.getByRole("button", { name: "Einplanen" }));

    await waitFor(() => expect(mocked.updateSchedule).toHaveBeenCalledOnce());
    const [, payload] = mocked.updateSchedule.mock.calls[0];
    expect(payload.occupancies).toHaveLength(1);
    const occ = payload.occupancies[0];
    // End derives from the recipe's fermentation duration (8 days).
    const span =
      new Date(occ.end_at).getTime() - new Date(occ.start_at).getTime();
    expect(span).toBe(8 * 86_400_000);
  });
});

describe("ScheduleDialog (Rezept-Abweichungen)", () => {
  it("leitet das Gärende aus dem Override ab, nicht aus dem Rezept", async () => {
    // Rezept: 8 Tage — Override: 3 Tage. Der PUT muss 3 Tage schicken.
    const lead = sud({
      occupancies: [],
      recipe_overrides: { fermentation_duration_days: 3 },
    });
    mocked.updateSchedule.mockResolvedValue(lead);

    render(
      <ScheduleDialog
        sud={lead}
        tanks={[F30]}
        sude={[lead]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    expect(screen.getByText(/Gärdauer laut Abweichung: 3 Tage/)).toBeInTheDocument();
    fireEvent.change(screen.getAllByRole("combobox")[0], {
      target: { value: F30.id },
    });
    fireEvent.click(screen.getByRole("button", { name: "Einplanen" }));

    await waitFor(() => expect(mocked.updateSchedule).toHaveBeenCalledOnce());
    const [, payload] = mocked.updateSchedule.mock.calls[0];
    const occ = payload.occupancies[0];
    const days =
      (new Date(occ.end_at).getTime() - new Date(occ.start_at).getTime()) /
      86_400_000;
    expect(days).toBeCloseTo(3, 5);
  });
});

describe("WithdrawDialog (Fass-Stückzahlen)", () => {
  it("rechnet Stückzahlen in hl um und schickt kegs statt volume_hl", async () => {
    const lead = sud({ occupancies: [storageOcc] });
    mocked.withdraw.mockResolvedValue(lead);
    render(
      <WithdrawDialog
        sud={lead}
        occupancy={storageOcc}
        tanks={[STORAGE_TANK]}
        sude={[lead]}
        kind="keg_fill"
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    fireEvent.change(screen.getByLabelText("Fässer 50 l (Stück)"), {
      target: { value: "4" },
    });
    fireEvent.change(screen.getByLabelText("Fässer 20 l (Stück)"), {
      target: { value: "3" },
    });
    expect(screen.getByText(/Ergibt 2.6 hl/)).toBeInTheDocument();

    // 30-l-Fässer sind vorerst nicht im Angebot (2026-08-05).
    expect(screen.queryByLabelText("Fässer 30 l (Stück)")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Abfüllen" }));
    await waitFor(() => expect(mocked.withdraw).toHaveBeenCalledOnce());
    const [, payload] = mocked.withdraw.mock.calls[0];
    expect(payload.kegs).toEqual([
      { size_l: 20, count: 3 },
      { size_l: 50, count: 4 },
    ]);
    expect(payload.volume_hl).toBeUndefined();
  });

  it("sperrt bei Überziehung über die Restmenge", () => {
    const lead = sud({ occupancies: [storageOcc] });  // 15 hl remain
    render(
      <WithdrawDialog
        sud={lead}
        occupancy={storageOcc}
        tanks={[STORAGE_TANK]}
        sude={[lead]}
        kind="keg_fill"
        onClose={() => {}}
        onDone={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText("Fässer 50 l (Stück)"), {
      target: { value: "40" },  // 20 hl > 15 hl
    });
    expect(screen.getByRole("button", { name: "Abfüllen" })).toBeDisabled();
  });

  it("Ausschank behält das direkte hl-Feld", () => {
    const lead = sud({ occupancies: [storageOcc] });
    render(
      <WithdrawDialog
        sud={lead}
        occupancy={storageOcc}
        tanks={[STORAGE_TANK]}
        sude={[lead]}
        kind="ausschank"
        onClose={() => {}}
        onDone={() => {}}
      />,
    );
    expect(screen.getByLabelText("Menge (hl)")).toBeInTheDocument();
    expect(screen.queryByLabelText("Fässer 50 l (Stück)")).toBeNull();
  });
});

describe("ReplanDialog (Tankkette)", () => {
  const toLocal = (iso: string) => {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };
  const ferm: Occupancy = {
    id: "occ-f",
    sud_id: "sud-1",
    tank_id: F30.id,
    stage: "fermentation_closed",
    start_at: "2026-09-01T07:00:00Z",
    end_at: "2026-09-08T12:00:00Z",
    volume_hl: null,
  };
  const lager: Occupancy = {
    id: "occ-l",
    sud_id: "sud-1",
    tank_id: STORAGE_TANK.id,
    stage: "storage",
    start_at: "2026-09-08T12:00:00Z",
    end_at: "2026-09-29T12:00:00Z",
    volume_hl: null,
  };
  const geplant = () => sud({ status: "planned", occupancies: [ferm, lager] });
  const alleTanks = [F30, F15, STORAGE_TANK, A100, A80];

  it("zeigt die Kette als Stationen und schickt sie verkettet ab", async () => {
    const planned = geplant();
    render(
      <ReplanDialog
        sud={planned}
        tanks={alleTanks}
        sude={[planned]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    // Bestehende Kette vorbelegt: Gärtank → Lagertank.
    expect(screen.getByLabelText("Station 1")).toHaveValue(F30.id);
    expect(screen.getByLabelText("Station 2")).toHaveValue(STORAGE_TANK.id);

    // Dritte Station anhängen: Ausschank, offen — wie beim Aufteilen.
    fireEvent.click(screen.getByRole("button", { name: "+ Station" }));
    fireEvent.change(screen.getByLabelText("Station 3"), {
      target: { value: A100.id },
    });
    fireEvent.change(screen.getByLabelText("Von 3"), {
      target: { value: toLocal("2026-09-29T12:00:00Z") },
    });
    fireEvent.change(screen.getByLabelText("Ende der letzten Station"), {
      target: { value: "" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Umplanen" }));

    await waitFor(() => expect(mocked.updateSchedule).toHaveBeenCalled());
    const [sudId, payload] = mocked.updateSchedule.mock.calls[0];
    expect(sudId).toBe("sud-1");
    const kette = payload.occupancies;
    expect(kette).toHaveLength(3);
    // Stufe kommt aus dem gewählten Tank; Ende = Start der nächsten Station.
    expect(kette[0]).toMatchObject({
      tank_id: F30.id,
      stage: "fermentation_closed",
    });
    expect(kette[0].end_at).toBe(kette[1].start_at);
    expect(kette[1]).toMatchObject({ tank_id: STORAGE_TANK.id, stage: "storage" });
    expect(kette[1].end_at).toBe(kette[2].start_at);
    expect(kette[2]).toMatchObject({
      tank_id: A100.id,
      stage: "ausschank",
      end_at: null,
      volume_hl: 15,
    });
  });

  it("Station entfernen kürzt die Kette; das Ende bleibt am letzten Glied", async () => {
    const planned = geplant();
    render(
      <ReplanDialog
        sud={planned}
        tanks={alleTanks}
        sude={[planned]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Station 2 entfernen" }));
    fireEvent.click(screen.getByRole("button", { name: "Umplanen" }));

    await waitFor(() => expect(mocked.updateSchedule).toHaveBeenCalled());
    const [, payload] = mocked.updateSchedule.mock.calls[0];
    expect(payload.occupancies).toHaveLength(1);
    expect(payload.occupancies[0].tank_id).toBe(F30.id);
    // Das vorbelegte Ende (29.09.) hängt jetzt an der einzigen Station.
    expect(payload.occupancies[0].end_at).toBe(
      new Date("2026-09-29T12:00:00Z").toISOString(),
    );
  });

  it("sperrt Absenden, wenn die Stationen nicht aufeinander folgen", () => {
    const planned = geplant();
    render(
      <ReplanDialog
        sud={planned}
        tanks={alleTanks}
        sude={[planned]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    fireEvent.change(screen.getByLabelText("Von 2"), {
      target: { value: toLocal("2026-08-30T12:00:00Z") },
    });
    expect(
      screen.getByText(/müssen zeitlich aufeinander folgen/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Umplanen" })).toBeDisabled();
  });
});
