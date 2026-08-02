import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import type { Occupancy, Sud, Tank } from "../api/types";
import { ScheduleDialog } from "./ScheduleDialog";
import { TransferDialog } from "./TransferDialog";
import { WithdrawDialog } from "./WithdrawDialog";

vi.mock("../api/client", () => ({
  api: {
    transferSud: vi.fn(),
    withdraw: vi.fn(),
    updateSchedule: vi.fn(),
  },
}));

import { api } from "../api/client";

const mocked = api as unknown as {
  transferSud: ReturnType<typeof vi.fn>;
  withdraw: ReturnType<typeof vi.fn>;
  updateSchedule: ReturnType<typeof vi.fn>;
};

const STORAGE_TANK: Tank = {
  id: "tank-s1",
  name: "S-30-1",
  cellar: "main",
  stage: "storage",
  capacity_hl: 30,
  active: true,
};

const A100: Tank = {
  id: "tank-a100",
  name: "A-100",
  cellar: "main",
  stage: "ausschank",
  capacity_hl: 100,
  active: true,
};

const A80: Tank = {
  id: "tank-a80",
  name: "A-80",
  cellar: "main",
  stage: "ausschank",
  capacity_hl: 80,
  active: true,
};

const F30: Tank = {
  id: "tank-f30",
  name: "F-30-1",
  cellar: "main",
  stage: "fermentation_closed",
  capacity_hl: 30,
  active: true,
};

const F15: Tank = {
  id: "tank-f15",
  name: "F-15-1",
  cellar: "main",
  stage: "fermentation_closed",
  capacity_hl: 15,
  active: true,
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
  },
  brew_date: "2026-08-01",
  status: "storing",
  notes: null,
  brewmaster: null,
  style_year_number: 1,
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
  mocked.updateSchedule.mockReset().mockResolvedValue(sud({}));
});

describe("TransferDialog (Ausschank split)", () => {
  it("splits volumes across tanks and sends them once the sum matches", async () => {
    const lead = sud({ occupancies: [storageOcc] });
    const partner = sud({
      id: "sud-2",
      style_year_number: 2,
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

    // 30 hl combined: 20 into A-100, add a row, 10 into A-80.
    fireEvent.change(screen.getByLabelText("Ausschanktank 1"), {
      target: { value: A100.id },
    });
    fireEvent.change(screen.getByLabelText("Volumen 1 (hl)"), {
      target: { value: "20" },
    });
    fireEvent.click(screen.getByRole("button", { name: "+ Tank aufteilen" }));
    fireEvent.change(screen.getByLabelText("Ausschanktank 2"), {
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
        tanks={[A100]}
        sude={[lead]}
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    fireEvent.change(screen.getByLabelText("Ausschanktank 1"), {
      target: { value: A100.id },
    });
    fireEvent.change(screen.getByLabelText("Volumen 1 (hl)"), {
      target: { value: "9" },
    });

    expect(screen.getByRole("button", { name: "Umdrücken" })).toBeDisabled();
    expect(mocked.transferSud).not.toHaveBeenCalled();
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
        onClose={() => {}}
        onDone={() => {}}
      />,
    );

    const input = screen.getByLabelText("Menge (hl)");
    fireEvent.change(input, { target: { value: "20" } });
    expect(screen.getByRole("button", { name: "Abfüllen" })).toBeDisabled();

    fireEvent.change(input, { target: { value: "5" } });
    fireEvent.click(screen.getByRole("button", { name: "Abfüllen" }));

    await waitFor(() => expect(mocked.withdraw).toHaveBeenCalledOnce());
    const [, payload] = mocked.withdraw.mock.calls[0];
    expect(payload.tank_id).toBe(STORAGE_TANK.id);
    expect(payload.volume_hl).toBe(5);
    expect(typeof payload.at).toBe("string");
  });
});

describe("ScheduleDialog", () => {
  it("offers only fermenters that fit the combined merged-batch volume", async () => {
    const lead = sud({ id: "sud-1", occupancies: [] });
    const partner = sud({
      id: "sud-2",
      style_year_number: 2,
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
