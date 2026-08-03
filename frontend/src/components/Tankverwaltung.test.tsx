import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";

import type { Location, Tank } from "../api/types";

vi.mock("../api/client", () => ({
  api: {
    createTank: vi.fn(),
    updateTank: vi.fn(),
    deleteTank: vi.fn(),
    createLocation: vi.fn(),
    updateLocation: vi.fn(),
    deleteLocation: vi.fn(),
  },
}));

import { api } from "../api/client";
import { Tankverwaltung } from "./Tankverwaltung";

const mocked = api as unknown as {
  createTank: ReturnType<typeof vi.fn>;
  updateTank: ReturnType<typeof vi.fn>;
  deleteTank: ReturnType<typeof vi.fn>;
  createLocation: ReturnType<typeof vi.fn>;
  updateLocation: ReturnType<typeof vi.fn>;
  deleteLocation: ReturnType<typeof vi.fn>;
};

const HAUPT: Location = { id: "loc-1", name: "Hauptkeller", position: 1 };
const NEBEN: Location = { id: "loc-2", name: "Nebenkeller", position: 2 };

const tank = (over: Partial<Tank>): Tank => ({
  id: "t-1",
  name: "S-30-1",
  location_id: "loc-1",
  stage: "storage",
  capacity_hl: 30,
  active: true,
  locked: false,
  ...over,
});

beforeEach(() => {
  mocked.createTank.mockReset().mockResolvedValue(tank({}));
  mocked.updateTank.mockReset().mockResolvedValue(tank({}));
  mocked.deleteTank.mockReset().mockResolvedValue(undefined);
  mocked.createLocation.mockReset().mockResolvedValue(HAUPT);
  mocked.updateLocation.mockReset().mockResolvedValue(HAUPT);
  mocked.deleteLocation.mockReset().mockResolvedValue(undefined);
});

test("gruppiert Tanks nach Standort und zeigt Ausgeblendete separat", () => {
  const tanks = [
    tank({ id: "t-1", name: "S-30-1", location_id: "loc-1" }),
    tank({ id: "t-2", name: "A2-35-1", location_id: "loc-2", stage: "ausschank" }),
    tank({ id: "t-3", name: "ALT-1", location_id: "loc-1", active: false }),
  ];
  render(
    <Tankverwaltung tanks={tanks} locations={[HAUPT, NEBEN]} onReload={() => {}} />,
  );

  expect(screen.getByText("Hauptkeller")).toBeInTheDocument();
  expect(screen.getByText("Nebenkeller")).toBeInTheDocument();
  expect(screen.getByText("S-30-1")).toBeInTheDocument();
  expect(screen.getByText("A2-35-1")).toBeInTheDocument();
  expect(screen.getByText("Ausgeblendet")).toBeInTheDocument();
  expect(screen.getByText("ALT-1")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Wieder aktivieren" }),
  ).toBeInTheDocument();
});

test("legt einen neuen Tank über den Dialog an", async () => {
  const onReload = vi.fn();
  render(
    <Tankverwaltung
      tanks={[tank({})]}
      locations={[HAUPT, NEBEN]}
      onReload={onReload}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "+ Tank" }));
  const dialog = screen.getByRole("dialog", { name: "Tank anlegen" });
  fireEvent.change(within(dialog).getByLabelText("Name"), {
    target: { value: "F-NEU-20" },
  });
  fireEvent.change(within(dialog).getByLabelText("Standort"), {
    target: { value: "loc-2" },
  });
  fireEvent.change(within(dialog).getByLabelText("Typ"), {
    target: { value: "fermentation_closed" },
  });
  fireEvent.change(within(dialog).getByLabelText("Kapazität (hl)"), {
    target: { value: "20" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Speichern" }));

  await waitFor(() => expect(mocked.createTank).toHaveBeenCalledOnce());
  expect(mocked.createTank).toHaveBeenCalledWith({
    name: "F-NEU-20",
    location_id: "loc-2",
    stage: "fermentation_closed",
    capacity_hl: 20,
  });
  await waitFor(() => expect(onReload).toHaveBeenCalled());
});

test("entfernt einen Tank erst nach zweitem Tipp", async () => {
  const onReload = vi.fn();
  render(
    <Tankverwaltung tanks={[tank({})]} locations={[HAUPT]} onReload={onReload} />,
  );

  fireEvent.click(screen.getByText("S-30-1"));
  const dialog = screen.getByRole("dialog", { name: "Tank bearbeiten" });

  fireEvent.click(within(dialog).getByRole("button", { name: "Entfernen" }));
  expect(mocked.deleteTank).not.toHaveBeenCalled();

  fireEvent.click(within(dialog).getByRole("button", { name: "Ja, entfernen" }));
  await waitFor(() => expect(mocked.deleteTank).toHaveBeenCalledWith("t-1"));
  await waitFor(() => expect(onReload).toHaveBeenCalled());
});

test("aktiviert ausgeblendete Tanks wieder", async () => {
  const onReload = vi.fn();
  render(
    <Tankverwaltung
      tanks={[tank({ id: "t-9", name: "ALT-2", active: false })]}
      locations={[HAUPT]}
      onReload={onReload}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Wieder aktivieren" }));
  await waitFor(() =>
    expect(mocked.updateTank).toHaveBeenCalledWith("t-9", { active: true }),
  );
  await waitFor(() => expect(onReload).toHaveBeenCalled());
});

test("legt einen neuen Standort an", async () => {
  const onReload = vi.fn();
  render(<Tankverwaltung tanks={[]} locations={[HAUPT]} onReload={onReload} />);

  fireEvent.click(screen.getByRole("button", { name: "+ Standort" }));
  const dialog = screen.getByRole("dialog", { name: "Standort anlegen" });
  fireEvent.change(within(dialog).getByLabelText("Name"), {
    target: { value: "Festzelt" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Speichern" }));

  await waitFor(() =>
    expect(mocked.createLocation).toHaveBeenCalledWith({ name: "Festzelt" }),
  );
  await waitFor(() => expect(onReload).toHaveBeenCalled());
});

test("benennt einen Standort um; Entfernen ist bei vorhandenen Tanks gesperrt", async () => {
  const onReload = vi.fn();
  render(
    <Tankverwaltung
      tanks={[tank({ location_id: "loc-1" })]}
      locations={[HAUPT]}
      onReload={onReload}
    />,
  );

  fireEvent.click(
    screen.getByRole("button", { name: "Standort Hauptkeller bearbeiten" }),
  );
  const dialog = screen.getByRole("dialog", { name: "Standort bearbeiten" });
  expect(
    within(dialog).getByRole("button", { name: /Entfernen \(Tanks vorhanden\)/ }),
  ).toBeDisabled();

  fireEvent.change(within(dialog).getByLabelText("Name"), {
    target: { value: "Bergkeller" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Speichern" }));

  await waitFor(() =>
    expect(mocked.updateLocation).toHaveBeenCalledWith("loc-1", {
      name: "Bergkeller",
    }),
  );
  await waitFor(() => expect(onReload).toHaveBeenCalled());
});

test("gesperrter Tank: Felder schreibgeschützt, Entsperren möglich", async () => {
  const onReload = vi.fn();
  render(
    <Tankverwaltung
      tanks={[tank({ locked: true })]}
      locations={[HAUPT]}
      onReload={onReload}
    />,
  );

  expect(screen.getByText("🔒 S-30-1")).toBeInTheDocument();
  fireEvent.click(screen.getByText("🔒 S-30-1"));
  const dialog = screen.getByRole("dialog", { name: "Tank bearbeiten" });

  expect(within(dialog).getByLabelText("Name")).toBeDisabled();
  expect(within(dialog).getByRole("button", { name: "Speichern" })).toBeDisabled();
  expect(within(dialog).queryByRole("button", { name: "Entfernen" })).toBeNull();

  fireEvent.click(within(dialog).getByRole("button", { name: "🔓 Entsperren" }));
  await waitFor(() =>
    expect(mocked.updateTank).toHaveBeenCalledWith("t-1", { locked: false }),
  );
  await waitFor(() => expect(onReload).toHaveBeenCalled());
});

test("Sperren aus dem Bearbeiten-Dialog heraus", async () => {
  render(
    <Tankverwaltung tanks={[tank({})]} locations={[HAUPT]} onReload={() => {}} />,
  );

  fireEvent.click(screen.getByText("S-30-1"));
  const dialog = screen.getByRole("dialog", { name: "Tank bearbeiten" });
  fireEvent.click(within(dialog).getByRole("button", { name: "🔒 Sperren" }));
  await waitFor(() =>
    expect(mocked.updateTank).toHaveBeenCalledWith("t-1", { locked: true }),
  );
});
