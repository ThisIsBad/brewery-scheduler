import type {
  Recipe,
  ScheduleIn,
  Sud,
  SudCreateIn,
  Tank,
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
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listTanks: () => request<Tank[]>("/api/tanks"),
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
