import { useMemo } from "react";
import Timeline, {
  type TimelineGroupBase,
  type TimelineItemBase,
} from "react-calendar-timeline";
import moment, { type Moment } from "moment";
import "react-calendar-timeline/lib/Timeline.css";

import type { Occupancy, Sud, Tank } from "../api/types";

interface ScheduleBoardProps {
  tanks: Tank[];
  sude: Sud[];
  onMoveOccupancy: (
    sudId: string,
    occupancyId: string,
    nextTankId: string,
    nextStartMs: number,
  ) => void;
}

interface BoardItem extends TimelineItemBase<Moment> {
  sudId: string;
  occupancyId: string;
}

const STAGE_LABEL: Record<string, string> = {
  fermentation_open: "Gärtank (offen)",
  fermentation_closed: "Gärtank",
  storage: "Lager",
  ausschank: "Ausschank",
};

const STYLE_COLOR: Record<string, string> = {
  kellerbier: "#c79144",
  wheat: "#e6c35a",
  festbier: "#8b3a1a",
  special: "#5b6f8a",
};

export function ScheduleBoard({ tanks, sude, onMoveOccupancy }: ScheduleBoardProps) {
  const groups: TimelineGroupBase[] = useMemo(
    () =>
      tanks
        // Deactivated tanks keep their row only while history references
        // them — brand-new plans should not land there.
        .filter(
          (t) =>
            t.active ||
            sude.some((s) => s.occupancies.some((o) => o.tank_id === t.id)),
        )
        .map((t) => ({
          id: t.id,
          title: `${t.name} · ${t.capacity_hl} hl · ${STAGE_LABEL[t.stage] ?? t.stage}`,
        })),
    [tanks, sude],
  );

  const items: BoardItem[] = useMemo(() => {
    // Merged-batch partners carry no occupancies of their own — their brew
    // numbers are folded into the lead's block title ("Nr. 1+2/2026") so the
    // merge is visible on the board.
    const partnerNumbersByLead = new Map<string, number[]>();
    for (const sud of sude) {
      if (sud.merged_into_sud_id) {
        const list = partnerNumbersByLead.get(sud.merged_into_sud_id) ?? [];
        list.push(sud.style_year_number);
        partnerNumbersByLead.set(sud.merged_into_sud_id, list);
      }
    }

    const result: BoardItem[] = [];
    for (const sud of sude) {
      for (const occ of sud.occupancies) {
        result.push(buildItem(sud, occ, partnerNumbersByLead.get(sud.id) ?? []));
      }
    }
    return result;
  }, [sude]);

  const defaultStart = moment().subtract(7, "days").startOf("day");
  const defaultEnd = moment().add(21, "days").startOf("day");

  return (
    <Timeline
      groups={groups}
      items={items}
      defaultTimeStart={defaultStart}
      defaultTimeEnd={defaultEnd}
      canMove
      canResize="both"
      stackItems
      lineHeight={36}
      onItemMove={(itemId, dragTime, newGroupOrder) => {
        const item = items.find((i) => i.id === itemId);
        if (!item) return;
        const nextGroup = groups[newGroupOrder];
        if (!nextGroup) return;
        onMoveOccupancy(item.sudId, item.occupancyId, String(nextGroup.id), dragTime);
      }}
    />
  );
}

function buildItem(sud: Sud, occ: Occupancy, partnerNumbers: number[]): BoardItem {
  const start = moment(occ.start_at);
  const end = occ.end_at
    ? moment(occ.end_at)
    : start.clone().add(durationDays(sud, occ), "days");
  const color = STYLE_COLOR[sud.recipe.beer_style] ?? "#888";
  const year = moment(sud.brew_date).year();
  const numbers = [sud.style_year_number, ...partnerNumbers].sort((a, b) => a - b);
  const sudNr = `Nr. ${numbers.join("+")}/${year}`;
  const stage = STAGE_LABEL[occ.stage] ?? occ.stage;

  return {
    id: occ.id,
    group: occ.tank_id,
    title: `${sud.recipe.name} ${sudNr} · ${stage}`,
    start_time: start,
    end_time: end,
    sudId: sud.id,
    occupancyId: occ.id,
    itemProps: {
      style: {
        background: color,
        color: "#fff",
        borderRadius: 4,
        border: "1px solid rgba(0,0,0,0.2)",
        fontSize: 12,
      },
    },
  };
}

function durationDays(sud: Sud, occ: Occupancy): number {
  // Phase 1 fallback: open occupancies (no end_at) get rendered with their
  // recipe-default duration so the Gantt isn't empty. Phase 2 will replace
  // this with explicit end_at values written by the validator.
  switch (occ.stage) {
    case "fermentation_open":
      return sud.recipe.open_fermentation_duration_days ?? 4;
    case "fermentation_closed":
      return sud.recipe.fermentation_duration_days;
    case "storage":
      return sud.recipe.storage_duration_days;
    case "ausschank":
      return 14;
    default:
      return 7;
  }
}
