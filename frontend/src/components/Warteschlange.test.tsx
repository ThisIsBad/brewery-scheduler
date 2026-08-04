import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import { enqueue } from "../api/queue";
import { Warteschlange } from "./Warteschlange";

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

afterEach(() => {
  localStorage.clear();
});

test("zeigt wartende Buchungen und sendet sie auf Tippen nach", async () => {
  enqueue("/api/sude/a/transfer", { method: "POST", body: "{}" });
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("{}", { status: 200 })),
  );
  const onReplayed = vi.fn();

  render(<Warteschlange onReplayed={onReplayed} />);
  expect(screen.getByText(/1 Buchung wartet auf Netz/)).toBeInTheDocument();
  expect(screen.getByText(/Umdrücken/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Jetzt senden" }));
  await waitFor(() => expect(onReplayed).toHaveBeenCalled());
  await waitFor(() =>
    expect(screen.queryByText(/wartet auf Netz/)).not.toBeInTheDocument(),
  );
});

test("zeigt Konflikte mit Grund und lässt sie verwerfen", async () => {
  enqueue("/api/sude/a/withdraw", { method: "POST", body: "{}" });
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ detail: "Nur 3 hl verfügbar." }), {
          status: 409,
        }),
    ),
  );

  render(<Warteschlange onReplayed={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "Jetzt senden" }));

  await waitFor(() =>
    expect(screen.getByText(/wurde abgelehnt: Nur 3 hl verfügbar\./)).toBeInTheDocument(),
  );
  fireEvent.click(screen.getByRole("button", { name: "Verwerfen" }));
  await waitFor(() =>
    expect(screen.queryByText(/abgelehnt/)).not.toBeInTheDocument(),
  );
});
