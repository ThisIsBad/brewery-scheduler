import type {
  Recipe,
  ScheduleIn,
  Sud,
  SudCreateIn,
  Tank,
  TankCreateIn,
  TankUpdateIn,
  TransferIn,
  WithdrawIn,
} from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
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
  listSude: () => request<Sud[]>("/api/sude"),
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
};
