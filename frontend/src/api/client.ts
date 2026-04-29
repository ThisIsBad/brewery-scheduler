import type { ScheduleIn, Sud, Tank } from "./types";

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
  updateSchedule: (sudId: string, payload: ScheduleIn) =>
    request<Sud>(`/api/sude/${sudId}/schedule`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
};
