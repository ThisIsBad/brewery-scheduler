import type {
  Location,
  LocationCreateIn,
  LocationUpdateIn,
  Recipe,
  RecipeCreateIn,
  RecipeStyleActiveIn,
  RecipeStyleFarbeIn,
  ScheduleIn,
  TankWithdrawIn,
  Sud,
  SudCreateIn,
  Tank,
  TankCreateIn,
  TankUpdateIn,
  TransferIn,
  Verlaufseintrag,
  WithdrawIn,
} from "./types";

import { QueuedError, enqueue, labelFor } from "./queue";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch (err) {
    // Netz weg, Request hat den Server nie erreicht. Lesezugriffe bedient
    // der Service-Worker-Cache; Buchungen landen in der Warteschlange
    // (issue #10) und werden bei Rückkehr des Netzes nachgesendet.
    const method = init?.method ?? "GET";
    if (method !== "GET") {
      enqueue(path, init ?? {});
      throw new QueuedError(labelFor(path, method));
    }
    throw err;
  }
  if (!res.ok) {
    const body = await res.text();
    // Surface the API's structured `detail` sentence instead of a raw JSON
    // blob — these messages are shown verbatim in the tap-flow dialogs.
    let message = `${res.status} ${res.statusText}`;
    try {
      const parsed = JSON.parse(body);
      if (typeof parsed.detail === "string") message = parsed.detail;
    } catch {
      if (body) message = `${message}: ${body}`;
    }
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  listTanks: () => request<Tank[]>("/api/tanks"),
  createTank: (payload: TankCreateIn) =>
    request<Tank>("/api/tanks", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateTank: (tankId: string, payload: TankUpdateIn) =>
    request<Tank>(`/api/tanks/${tankId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteTank: (tankId: string) =>
    request<void>(`/api/tanks/${tankId}`, { method: "DELETE" }),
  createRecipe: (payload: RecipeCreateIn) =>
    request<Recipe>("/api/recipes", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  setRecipeStyleActive: (payload: RecipeStyleActiveIn) =>
    request<Recipe[]>("/api/recipes/style-active", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  setRecipeStyleFarbe: (payload: RecipeStyleFarbeIn) =>
    request<Recipe[]>("/api/recipes/style-farbe", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  listLocations: () => request<Location[]>("/api/locations"),
  createLocation: (payload: LocationCreateIn) =>
    request<Location>("/api/locations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateLocation: (locationId: string, payload: LocationUpdateIn) =>
    request<Location>(`/api/locations/${locationId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  deleteLocation: (locationId: string) =>
    request<void>(`/api/locations/${locationId}`, { method: "DELETE" }),
  ich: () => request<{ benutzer: string }>("/api/ich"),
  listSude: () => request<Sud[]>("/api/sude"),
  listVerlauf: (sudId?: string) =>
    request<Verlaufseintrag[]>(
      sudId ? `/api/verlauf?sud_id=${sudId}` : "/api/verlauf",
    ),
  listRecipes: () => request<Recipe[]>("/api/recipes"),
  createSud: (payload: SudCreateIn) =>
    request<Sud>("/api/sude", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  updateSchedule: (sudId: string, payload: ScheduleIn) =>
    request<Sud>(`/api/sude/${sudId}/schedule`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  transferSud: (sudId: string, payload: TransferIn) =>
    request<Sud>(`/api/sude/${sudId}/transfer`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  withdraw: (sudId: string, payload: WithdrawIn) =>
    request<Sud>(`/api/sude/${sudId}/withdraw`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  tankWithdraw: (tankId: string, payload: TankWithdrawIn) =>
    request<Sud[]>(`/api/tanks/${tankId}/withdraw`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
