import { useMemo, useState } from "react";

import type { Occupancy, Sud, Tank } from "../api/types";
import {
  STAGE_LABEL,
  dayProgressLabel,
  firstFutureOccupancy,
  formatDate,
  formatHl,
  nextStage,
  occupancyAt,
  remainingHl,
  sudNumberLabel,
} from "../domain";
import { ScheduleDialog } from "./ScheduleDialog";
import { TransferDialog } from "./TransferDialog";
import { WithdrawDialog } from "./WithdrawDialog";

interface KellerblickProps {
  tanks: Tank[];
  sude: Sud[];
  onChanged: (sud: Sud) => void;
}

type DialogState =
  | { kind: "transfer"; sud: Sud; occupancy: Occupancy }
  | { kind: "withdraw"; sud: Sud; occupancy: Occupancy }
  | { kind: "schedule"; sud: Sud }
  | null;

export function Kellerblick({ tanks, sude, onChanged }: KellerblickProps) {
  const [dialog, setDialog] = useState<DialogState>(null);
  const now = useMemo(() => new Date(), []);
  const tankById = useMemo(() => new Map(tanks.map((t) => [t.id, t])), [tanks]);

  const leads = sude.filter((s) => s.merged_into_sud_id === null);
  const current = leads
    .map((sud) => ({ sud, occ: occupancyAt(sud, now) }))
    .filter((x): x is { sud: Sud; occ: Occupancy } => x.occ !== null);
  const planned = leads
    .filter((sud) => occupancyAt(sud, now) === null)
    .map((sud) => ({ sud, occ: firstFutureOccupancy(sud, now) }))
    .filter((x): x is { sud: Sud; occ: Occupancy } => x.occ !== null);
  const unplanned = leads.filter((sud) => sud.occupancies.length === 0);

  return (
    <div className="kellerblick">
      <section>
        <h2>Jetzt im Keller</h2>
        {current.length === 0 && <p className="empty">Kein Tank belegt.</p>}
        {current.map(({ sud, occ }) => {
          const tank = tankById.get(occ.tank_id);
          const remaining = remainingHl(sud, sude, occ);
          const target = nextStage(occ.stage);
          return (
            <article className="card" key={occ.id}>
              <header>
                <strong>{tank?.name ?? "?"}</strong>
                <span className="muted">
                  {tank ? formatHl(tank.capacity_hl) : ""} ·{" "}
                  {STAGE_LABEL[occ.stage]}
                </span>
              </header>
              <div className="card-body">
                <div className="beer">
                  {sud.recipe.name} {sudNumberLabel(sud, sude)}
                </div>
                <div className="muted">
                  {dayProgressLabel(occ, now)}
                  {occ.end_at ? ` · bis ${formatDate(occ.end_at)}` : ""}
                  {" · "}noch {formatHl(remaining)}
                </div>
              </div>
              <footer>
                {target && (
                  <button
                    type="button"
                    onClick={() => setDialog({ kind: "transfer", sud, occupancy: occ })}
                  >
                    Umdrücken → {STAGE_LABEL[target]}
                  </button>
                )}
                <button
                  type="button"
                  className="secondary"
                  disabled={remaining <= 0}
                  onClick={() => setDialog({ kind: "withdraw", sud, occupancy: occ })}
                >
                  Fass abfüllen
                </button>
              </footer>
            </article>
          );
        })}
      </section>

      {planned.length > 0 && (
        <section>
          <h2>Geplant</h2>
          {planned.map(({ sud, occ }) => {
            const tank = tankById.get(occ.tank_id);
            return (
              <article className="card planned" key={occ.id}>
                <div className="card-body">
                  <div className="beer">
                    {sud.recipe.name} {sudNumberLabel(sud, sude)}
                  </div>
                  <div className="muted">
                    ab {formatDate(occ.start_at)} in {tank?.name ?? "?"} (
                    {STAGE_LABEL[occ.stage]})
                  </div>
                </div>
              </article>
            );
          })}
        </section>
      )}

      {unplanned.length > 0 && (
        <section>
          <h2>Ungeplant</h2>
          {unplanned.map((sud) => (
            <article className="card unplanned" key={sud.id}>
              <div className="card-body">
                <div className="beer">
                  {sud.recipe.name} {sudNumberLabel(sud, sude)}
                </div>
                <div className="muted">Sudtag {formatDate(sud.brew_date)}</div>
              </div>
              <footer>
                <button
                  type="button"
                  onClick={() => setDialog({ kind: "schedule", sud })}
                >
                  Einplanen
                </button>
              </footer>
            </article>
          ))}
        </section>
      )}

      {dialog?.kind === "transfer" && (
        <TransferDialog
          sud={dialog.sud}
          occupancy={dialog.occupancy}
          tanks={tanks}
          sude={sude}
          onClose={() => setDialog(null)}
          onDone={(updated) => {
            onChanged(updated);
            setDialog(null);
          }}
        />
      )}
      {dialog?.kind === "withdraw" && (
        <WithdrawDialog
          sud={dialog.sud}
          occupancy={dialog.occupancy}
          tanks={tanks}
          sude={sude}
          onClose={() => setDialog(null)}
          onDone={(updated) => {
            onChanged(updated);
            setDialog(null);
          }}
        />
      )}
      {dialog?.kind === "schedule" && (
        <ScheduleDialog
          sud={dialog.sud}
          tanks={tanks}
          onClose={() => setDialog(null)}
          onDone={(updated) => {
            onChanged(updated);
            setDialog(null);
          }}
        />
      )}
    </div>
  );
}
