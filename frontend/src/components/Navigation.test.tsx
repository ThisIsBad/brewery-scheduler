import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { api } from "../api/client";
import { Navigation, Profil } from "./Navigation";

beforeEach(() => {
  vi.restoreAllMocks();
});

test("die tägliche Navigation liegt unten und braucht einen Tipp", () => {
  const onView = vi.fn();
  render(<Navigation view="kellerblick" onView={onView} />);

  const leiste = screen.getByRole("navigation", { name: "Ansicht" });
  expect(
    [...leiste.querySelectorAll("button")].map((b) => b.textContent),
  ).toEqual(["Kellerblick", "Zeitplan", "Einkauf", "Mehr"]);

  fireEvent.click(screen.getByRole("button", { name: "Zeitplan" }));
  expect(onView).toHaveBeenCalledWith("zeitplan");
});

test("Seltenes steckt hinter Mehr und schließt das Blatt beim Wählen", () => {
  const onView = vi.fn();
  render(<Navigation view="kellerblick" onView={onView} />);

  fireEvent.click(screen.getByRole("button", { name: "Mehr" }));
  fireEvent.click(screen.getByRole("button", { name: "Rezepte" }));

  expect(onView).toHaveBeenCalledWith("rezepte");
  expect(screen.queryByRole("dialog", { name: "Mehr" })).not.toBeInTheDocument();
});

test("Mehr bleibt markiert, solange man in einer seiner Ansichten steht", () => {
  render(<Navigation view="verlauf" onView={() => {}} />);

  const mehr = screen.getByRole("button", { name: "Mehr" });
  expect(mehr).toHaveClass("active");
  expect(mehr).toHaveAttribute("aria-current", "page");
});

test("das Profilsymbol nennt den angemeldeten Benutzer beim Antippen", async () => {
  vi.spyOn(api, "ich").mockResolvedValue({ benutzer: "vincenz" });
  render(<Profil />);

  // Vor dem Antippen steht der Name nur in der Beschriftung fürs Vorlesen.
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Angemeldet als vincenz" }),
    ).toBeInTheDocument(),
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Angemeldet als vincenz" }));
  expect(screen.getByRole("dialog", { name: "Profil" })).toBeInTheDocument();
  expect(screen.getByText("vincenz")).toBeInTheDocument();
});

test("ein Fehler beim Abruf lässt das Symbol stehen statt die App zu kippen", async () => {
  vi.spyOn(api, "ich").mockRejectedValue(new Error("offline"));
  render(<Profil />);

  const knopf = await screen.findByRole("button", { name: "Profil" });
  fireEvent.click(knopf);
  expect(screen.getByText("unbekannt")).toBeInTheDocument();
});
