import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { Absturzanzeige } from "./Absturzanzeige";

function Bombe(): never {
  throw new Error("Kaputt: Testabsturz");
}

test("zeigt Kinder, solange nichts abstürzt", () => {
  render(
    <Absturzanzeige>
      <p>Alles gut im Keller</p>
    </Absturzanzeige>,
  );
  expect(screen.getByText("Alles gut im Keller")).toBeInTheDocument();
});

test("zeigt Fehlermeldung statt weißer Seite, wenn ein Kind abstürzt", () => {
  // React logs the (intentional) crash to console.error — keep test output clean.
  const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
  try {
    render(
      <Absturzanzeige>
        <Bombe />
      </Absturzanzeige>,
    );
  } finally {
    quiet.mockRestore();
  }
  expect(screen.getByText("⚠️ Die App ist abgestürzt")).toBeInTheDocument();
  expect(screen.getByText("Kaputt: Testabsturz")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Neu laden" })).toBeInTheDocument();
});
