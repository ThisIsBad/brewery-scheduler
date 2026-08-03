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
  // brew_date is a date-only string; slicing avoids the UTC-midnight parse
  // that would shift Jan 1 into the previous year west of UTC.
  const year = lead.brew_date.slice(0, 4);
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

/** Everything that ever left this batch — kegs and pours, all tanks. */
export function totalWithdrawnHl(lead: Sud): number {
  return lead.withdrawals.reduce((sum, w) => sum + w.volume_hl, 0);
}

/** The volume that physically still exists: brewed minus withdrawn.
 * This is what transfers move and what capacity checks work with. */
export function batchRemainingHl(lead: Sud, all: Sud[]): number {
  return combinedVolumeHl(lead, all) - totalWithdrawnHl(lead);
}

/** What is left of this batch in the given tank. Explicit allocations
 * (Ausschank splits) subtract only that tank's withdrawals; a whole-batch
 * occupancy subtracts everything ever withdrawn. Mirrors the backend. */
export function remainingHl(lead: Sud, all: Sud[], occ: Occupancy): number {
  if (occ.volume_hl !== null) {
    const tankWithdrawn = lead.withdrawals
      .filter((w) => w.tank_id === occ.tank_id)
      .reduce((sum, w) => sum + w.volume_hl, 0);
    return occ.volume_hl - tankWithdrawn;
  }
  return batchRemainingHl(lead, all);
}

/** "Alter: Tag N" — since the batch first entered any tank. */
export function ageLabel(sud: Sud, when: Date): string | null {
  if (sud.occupancies.length === 0) return null;
  const first = sud.occupancies.reduce((earliest, o) =>
    new Date(o.start_at) < new Date(earliest.start_at) ? o : earliest,
  );
  const midnight = (d: Date) =>
    new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const day =
    Math.round((midnight(when) - midnight(new Date(first.start_at))) / 86_400_000) +
    1;
  return `Alter: Tag ${Math.max(1, day)}`;
}

/** "Tag 3 von 7" within an occupancy window; "Tag 3" for open-ended ones.
 * Calendar-day based (local midnights): the morning round on the day after
 * a 14:00 start counts as Tag 2, matching how the brewmaster counts.
 * Math.round absorbs DST hour shifts. */
export function dayProgressLabel(occ: Occupancy, when: Date): string {
  const midnight = (d: Date) =>
    new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const start = new Date(occ.start_at);
  const day =
    Math.round((midnight(when) - midnight(start)) / 86_400_000) + 1;
  if (!occ.end_at) return `Tag ${day}`;
  const total = Math.max(
    1,
    Math.round((midnight(new Date(occ.end_at)) - midnight(start)) / 86_400_000),
  );
  return `Tag ${Math.min(day, total)} von ${total}`;
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
