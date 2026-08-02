// Domain helpers shared by the Kellerblick cards, the tap-flow dialogs and
// the schedule board. All volumes in hl (1 hl = 100 l).

import type { Occupancy, Sud, TankStage } from "./api/types";

export const STAGE_ORDER: TankStage[] = [
  "fermentation_open",
  "fermentation_closed",
  "storage",
  "ausschank",
];

export const STAGE_LABEL: Record<TankStage, string> = {
  fermentation_open: "Gärtank (offen)",
  fermentation_closed: "Gärtank",
  storage: "Lagertank",
  ausschank: "Ausschank",
};

export function stageRank(stage: TankStage): number {
  return STAGE_ORDER.indexOf(stage);
}

export function nextStage(stage: TankStage): TankStage | null {
  const idx = stageRank(stage);
  return idx >= 0 && idx < STAGE_ORDER.length - 1 ? STAGE_ORDER[idx + 1] : null;
}

/** Partners of a lead Sud (merged batches share the lead's tank). */
export function partnersOf(lead: Sud, all: Sud[]): Sud[] {
  return all.filter((s) => s.merged_into_sud_id === lead.id);
}

/** Lead + partner volume — what physically sits in the shared tank. */
export function combinedVolumeHl(lead: Sud, all: Sud[]): number {
  return (
    lead.volume_hl + partnersOf(lead, all).reduce((sum, p) => sum + p.volume_hl, 0)
  );
}

/** "Nr. 1+2/2026" — the lead's number plus its partners'. */
export function sudNumberLabel(lead: Sud, all: Sud[]): string {
  const numbers = [
    lead.style_year_number,
    ...partnersOf(lead, all).map((p) => p.style_year_number),
  ].sort((a, b) => a - b);
  const year = new Date(lead.brew_date).getFullYear();
  return `Nr. ${numbers.join("+")}/${year}`;
}

export function occupancyAt(sud: Sud, when: Date): Occupancy | null {
  const t = when.getTime();
  return (
    sud.occupancies.find((o) => {
      const start = new Date(o.start_at).getTime();
      const end = o.end_at ? new Date(o.end_at).getTime() : Infinity;
      return start <= t && t < end;
    }) ?? null
  );
}

export function firstFutureOccupancy(sud: Sud, when: Date): Occupancy | null {
  const t = when.getTime();
  const future = sud.occupancies
    .filter((o) => new Date(o.start_at).getTime() > t)
    .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime());
  return future[0] ?? null;
}

/** Allocation volume of an occupancy: explicit share or the whole batch. */
export function allocationHl(occ: Occupancy, lead: Sud, all: Sud[]): number {
  return occ.volume_hl ?? combinedVolumeHl(lead, all);
}

/** What is left of this batch in the given tank: allocation − withdrawals. */
export function remainingHl(
  lead: Sud,
  all: Sud[],
  occ: Occupancy,
): number {
  const withdrawn = lead.withdrawals
    .filter((w) => w.tank_id === occ.tank_id)
    .reduce((sum, w) => sum + w.volume_hl, 0);
  return allocationHl(occ, lead, all) - withdrawn;
}

/** "Tag 3 von 7" within an occupancy window; "Tag 3" for open-ended ones. */
export function dayProgressLabel(occ: Occupancy, when: Date): string {
  const start = new Date(occ.start_at).getTime();
  const day = Math.floor((when.getTime() - start) / 86_400_000) + 1;
  if (!occ.end_at) return `Tag ${day}`;
  const total = Math.ceil(
    (new Date(occ.end_at).getTime() - start) / 86_400_000,
  );
  return `Tag ${day} von ${total}`;
}

export function formatHl(volume: number): string {
  return `${Number.isInteger(volume) ? volume : volume.toFixed(1)} hl`;
}

export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
  });
}
