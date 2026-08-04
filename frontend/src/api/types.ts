// Mirror of the backend's Pydantic schemas (backend/src/brewery_scheduler/schemas.py).
// Keep in sync manually until we generate from the OpenAPI spec.

export interface Location {
  id: string;
  name: string;
  position: number;
}

export interface LocationCreateIn {
  name: string;
}

export interface LocationUpdateIn {
  name: string;
}

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
  location_id: string;
  stage: TankStage;
  capacity_hl: number;
  active: boolean;
  locked: boolean;
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
  created_at: string;
  created_by: string | null;
  notes: string | null;
  malts?: Malz[];
  hop_gaben?: Hopfengabe[];
  maischplan?: Maischrast[];
  wasser?: Wasser | null;
  yeast?: string | null;
  original_gravity_plato?: number | null;
  ibu?: number | null;
  color_ebc?: number | null;
  kochzeit_min?: number | null;
  karbonisierung_g_l?: number | null;
  anstellhinweis?: string | null;
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
  /** The brew moment (timestamp); brew_date is its server-derived day. */
  brew_at: string;
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
  /** Per-Sud deviations from the recipe (duration fields only). */
  recipe_overrides?: RecipeOverridesIn | null;
  occupancies: Occupancy[];
  withdrawals: Withdrawal[];
  /**
   * Non-blocking process hints from mutating endpoints (e.g. active yeast
   * entering an Ausschank tank). Empty on plain reads; optional so cached
   * pre-warning responses keep parsing.
   */
  warnings?: string[];
}

export interface TankCreateIn {
  name: string;
  location_id: string;
  stage: TankStage;
  capacity_hl: number;
}

export interface TankUpdateIn {
  name?: string;
  location_id?: string;
  stage?: TankStage;
  capacity_hl?: number;
  active?: boolean;
  locked?: boolean;
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
  /** Brew moment with time — several Sude share a brew day. */
  brew_at: string;
  notes?: string | null;
  brewmaster?: string | null;
  initial_occupancy?: ScheduleOccupancyIn;
  /** Create this Sud as a merged-batch partner of the given lead Sud. */
  merge_into_sud_id?: string | null;
  recipe_overrides?: RecipeOverridesIn;
}

export type WithdrawalKind = "keg_fill" | "ausschank";

export interface Malz {
  name: string;
  kg: number;
  /** Mälzerei (BM, Weyermann, Steinbach …) wie auf dem Brauzettel. */
  maelzerei?: string | null;
}

export interface Hopfengabe {
  name: string;
  gramm: number;
  /** Freitext wie auf dem Brauzettel: „Kochbeginn", „nach 55 min",
   * „Vorderwürze", „Whirlpool", „Kalthopfung Tag 2". */
  zeitpunkt: string;
  alpha_prozent?: number | null;
}

export interface Maischrast {
  /** Einmaischen, Rast, Abmaischen … */
  schritt: string;
  temp_c?: number | null;
  dauer_min?: number | null;
}

export interface Wasser {
  hauptguss_hl?: number | null;
  nachguss_hl?: number[];
}

export interface RecipeCreateIn {
  beer_style: BeerStyle;
  name: string;
  fermentation_duration_days: number;
  open_fermentation_required: boolean;
  open_fermentation_duration_days: number | null;
  storage_duration_days: number;
  max_storage_duration_days: number;
  notes?: string | null;
  created_by?: string | null;
  malts?: Malz[];
  hop_gaben?: Hopfengabe[];
  maischplan?: Maischrast[];
  wasser?: Wasser | null;
  yeast?: string | null;
  original_gravity_plato?: number | null;
  ibu?: number | null;
  color_ebc?: number | null;
  kochzeit_min?: number | null;
  karbonisierung_g_l?: number | null;
  anstellhinweis?: string | null;
}

export interface RecipeOverridesIn {
  fermentation_duration_days?: number;
  storage_duration_days?: number;
  open_fermentation_duration_days?: number;
}

export interface KegCount {
  size_l: number;
  count: number;
}

export interface Withdrawal {
  id: string;
  sud_id: string;
  tank_id: string;
  volume_hl: number;
  at: string;
  kind: WithdrawalKind;
  keg_counts?: KegCount[] | null;
  notes: string | null;
}

export interface WithdrawIn {
  tank_id: string;
  /** Direct volume — or omit it and send keg counts (keg fills only). */
  volume_hl?: number;
  kegs?: KegCount[];
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
  /** Tank the beer is pushed out of — scopes the move to that tank's
   * share when the batch is split across tanks. */
  from_tank_id?: string;
  allocations: TransferAllocationIn[];
}
