import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";

import type { Tank } from "../api/types";

vi.mock("../api/client", () => ({
  api: {
    createTank: vi.fn(),
    updateTank: vi.fn(),
    deleteTank: vi.fn(),
  },
}));

import { api } from "../api/client";
import { Tankverwaltung } from "./Tankverwaltung";

const mocked = api as unknown as {
  createTank: ReturnType<typeof vi.fn>;
  updateTank: ReturnType<typeof vi.fn>;
  deleteTank: ReturnType<typeof vi.fn>;
};

const tank = (over: Partial<Tank>): Tank => ({
  id: "t-1",
  name: "S-30-1",
  cellar: "main",
  stage: "storage",
  capacity_hl: 30,
  active: true,
  ...over,
});

beforeEach(() => {
  mocked.createTank.mockReset().mockResolvedValue(tank({}));
  mocked.updateTank.mockReset().mockResolvedValue(tank({}));
  mocked.deleteTank.mockReset().mockResolvedValue(undefined);
});

test("gruppiert Tanks nach Keller und zeigt Ausgeblendete separat", () => {
  const tanks = [
    tank({ id: "t-1", name: "S-30-1", cellar: "main" }),
    tank({ id: "t-2", name: "A2-35-1", cellar: "secondary", stage: "ausschank" }),
    tank({ id: "t-3", name: "ALT-1", cellar: "main", active: false }),
  ];
  render(<Tankverwaltung tanks={tanks} onReload={() => {}} />);

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
  render(<Tankverwaltung tanks={[tank({})]} onReload={onReload} />);

  fireEvent.click(screen.getByRole("button", { name: "+ Tank" }));
  const dialog = screen.getByRole("dialog", { name: "Tank anlegen" });
  fireEvent.change(within(dialog).getByLabelText("Name"), {
    target: { value: "F-NEU-20" },
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
    cellar: "main",
    stage: "fermentation_closed",
    capacity_hl: 20,
  });
  await waitFor(() => expect(onReload).toHaveBeenCalled());
});

test("entfernt einen Tank erst nach zweitem Tipp", async () => {
  const onReload = vi.fn();
  render(<Tankverwaltung tanks={[tank({})]} onReload={onReload} />);

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
      onReload={onReload}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Wieder aktivieren" }));
  await waitFor(() =>
    expect(mocked.updateTank).toHaveBeenCalledWith("t-9", { active: true }),
  );
  await waitFor(() => expect(onReload).toHaveBeenCalled());
});
