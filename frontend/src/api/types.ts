// Mirror of the backend's Pydantic schemas (backend/src/brewery_scheduler/schemas.py).
// Keep in sync manually until we generate from the OpenAPI spec.

export type TankCellar = "main" | "secondary";

export type TankStage =
  | "fermentation_open"
  | "fermentation_closed"
  | "storage"
  | "ausschank";

export type BeerStyle = "kellerbier" | "wheat" | "festbier" | "special";

export type SudStatus =
  | "planned"
  | "brewing"
  | "fermenting"
  | "storing"
  | "in_ausschank"
  | "served"
  | "discarded";

export interface Tank {
  id: string;
  name: string;
  cellar: TankCellar;
  stage: TankStage;
  capacity_hl: number;
  active: boolean;
}

export interface Recipe {
  id: string;
  beer_style: BeerStyle;
  version: number;
  name: string;
  fermentation_duration_days: number;
  open_fermentation_required: boolean;
  open_fermentation_duration_days: number | null;
  storage_duration_days: number;
  max_storage_duration_days: number;
}

export interface Occupancy {
  id: string;
  sud_id: string;
  tank_id: string;
  stage: TankStage;
  start_at: string;
  end_at: string | null;
  /** Volume share in hl; null = the full combined volume of the batch. */
  volume_hl: number | null;
}

export interface Sud {
  id: string;
  recipe_id: string;
  recipe: Recipe;
  brew_date: string;
  status: SudStatus;
  notes: string | null;
  brewmaster: string | null;
  /**
   * Sequential per (beer_style, year(brew_date)). Displayed on the Gantt
   * as the brewmaster-facing Sud-Nr (e.g. "Kellerbier 17/2026").
   *
   * The internal global_number is intentionally not exposed to the API.
   */
  style_year_number: number;
  volume_hl: number;
  /**
   * Merged batches (issue #3): when set, this Sud is a partner sharing its
   * lead's tank and carries no occupancies of its own.
   */
  merged_into_sud_id: string | null;
  occupancies: Occupancy[];
  withdrawals: Withdrawal[];
}

export interface ScheduleOccupancyIn {
  tank_id: string;
  stage: TankStage;
  start_at: string;
  end_at: string | null;
  volume_hl?: number | null;
}

export interface ScheduleIn {
  occupancies: ScheduleOccupancyIn[];
}

export interface SudCreateIn {
  recipe_id: string;
  brew_date: string;
  notes?: string | null;
  brewmaster?: string | null;
  initial_occupancy?: ScheduleOccupancyIn;
  /** Create this Sud as a merged-batch partner of the given lead Sud. */
  merge_into_sud_id?: string | null;
}

export type WithdrawalKind = "keg_fill" | "ausschank";

export interface Withdrawal {
  id: string;
  sud_id: string;
  tank_id: string;
  volume_hl: number;
  at: string;
  kind: WithdrawalKind;
  notes: string | null;
}

export interface WithdrawIn {
  tank_id: string;
  volume_hl: number;
  at: string;
  kind?: WithdrawalKind;
  notes?: string | null;
}

export interface TransferAllocationIn {
  tank_id: string;
  volume_hl?: number | null;
}

export interface TransferIn {
  start_at: string;
  end_at?: string | null;
  allocations: TransferAllocationIn[];
}
