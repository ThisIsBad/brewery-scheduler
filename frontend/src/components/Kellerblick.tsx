import { useEffect, useMemo, useState } from "react";

import type { Occupancy, Sud, Tank, WithdrawalKind } from "../api/types";
import {
  STAGE_LABEL,
  ageLabel,
  dayProgressLabel,
  firstFutureOccupancy,
  formatDate,
  formatHl,
  occupancyAt,
  remainingHl,
  sudNumberLabel,
} from "../domain";
import { ReplanDialog } from "./ReplanDialog";
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
  | { kind: "withdraw"; sud: Sud; occupancy: Occupancy; withdrawalKind: WithdrawalKind }
  | { kind: "replan"; sud: Sud; occupancy: Occupancy }
  | { kind: "schedule"; sud: Sud }
  | null;

export function Kellerblick({ tanks, sude, onChanged }: KellerblickProps) {
  const [dialog, setDialog] = useState<DialogState>(null);
  // Re-render every minute so cards move between sections while the phone
  // stays open on the cellar round — `now` is recomputed per render.
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 60_000);
    return () => clearInterval(id);
  }, []);
  const now = new Date();
  const tankById = useMemo(() => new Map(tanks.map((t) => [t.id, t])), [tanks]);

  const leads = sude.filter((s) => s.merged_into_sud_id === null);
  // A batch split across Ausschank tanks has several concurrent occupancies
  // — every occupied tank gets its own card.
  const current = leads.flatMap((sud) =>
    sud.occupancies
      .filter((o) => {
        const start = new Date(o.start_at).getTime();
        const end = o.end_at ? new Date(o.end_at).getTime() : Infinity;
        return start <= now.getTime() && now.getTime() < end;
      })
      .map((occ) => ({ sud, occ })),
  );
  const planned = leads
    .filter((sud) => occupancyAt(sud, now) === null)
    .map((sud) => ({ sud, occ: firstFutureOccupancy(sud, now) }))
    .filter((x): x is { sud: Sud; occ: Occupancy } => x.occ !== null);
  const unplanned = leads.filter((sud) => sud.occupancies.length === 0);
  // Past their planned window with nothing active or upcoming: exactly when
  // the Umdrücken is due, so these must stay visible and actionable.
  const overdue = leads
    .filter(
      (sud) =>
        sud.occupancies.length > 0 &&
        occupancyAt(sud, now) === null &&
        firstFutureOccupancy(sud, now) === null,
    )
    .map((sud) => ({
      sud,
      occ: sud.occupancies.reduce((latest, o) =>
        new Date(o.start_at) > new Date(latest.start_at) ? o : latest,
      ),
    }));

  return (
    <div className="kellerblick">
      <section>
        <h2>Jetzt im Keller</h2>
        {current.length === 0 && <p className="empty">Kein Tank belegt.</p>}
        {current.map(({ sud, occ }) => {
          const tank = tankById.get(occ.tank_id);
          const remaining = remainingHl(sud, sude, occ);
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
                  {dayProgressLabel(occ, now)} im Tank
                  {occ.end_at ? ` · bis ${formatDate(occ.end_at)}` : ""}
                  {" · "}noch {formatHl(remaining)}
                </div>
                <div className="muted">{ageLabel(sud, now)}</div>
              </div>
              <footer>
                <button
                  type="button"
                  onClick={() => setDialog({ kind: "transfer", sud, occupancy: occ })}
                >
                  Umdrücken
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={remaining <= 0}
                  onClick={() =>
                    setDialog({
                      kind: "withdraw",
                      sud,
                      occupancy: occ,
                      withdrawalKind: "keg_fill",
                    })
                  }
                >
                  Fass abfüllen
                </button>
                <button
                  type="button"
                  className="secondary"
                  disabled={remaining <= 0}
                  onClick={() =>
                    setDialog({
                      kind: "withdraw",
                      sud,
                      occupancy: occ,
                      withdrawalKind: "ausschank",
                    })
                  }
                >
                  Ausgeschenkt
                </button>
              </footer>
            </article>
          );
        })}
      </section>

      {overdue.length > 0 && (
        <section>
          <h2>Überfällig</h2>
          {overdue.map(({ sud, occ }) => {
            const tank = tankById.get(occ.tank_id);
            return (
              <article className="card overdue" key={occ.id}>
                <header>
                  <strong>{tank?.name ?? "?"}</strong>
                  <span className="muted">{STAGE_LABEL[occ.stage]}</span>
                </header>
                <div className="card-body">
                  <div className="beer">
                    {sud.recipe.name} {sudNumberLabel(sud, sude)}
                  </div>
                  <div className="muted">
                    geplantes Ende {occ.end_at ? formatDate(occ.end_at) : "—"} ist
                    vorbei — Bier steht noch im Tank
                  </div>
                </div>
                <footer>
                  <button
                    type="button"
                    onClick={() =>
                      setDialog({ kind: "transfer", sud, occupancy: occ })
                    }
                  >
                    Umdrücken
                  </button>
                </footer>
              </article>
            );
          })}
        </section>
      )}

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
                <footer>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setDialog({ kind: "replan", sud, occupancy: occ })}
                  >
                    Umplanen
                  </button>
                </footer>
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
          kind={dialog.withdrawalKind}
          onClose={() => setDialog(null)}
          onDone={(updated) => {
            onChanged(updated);
            setDialog(null);
          }}
        />
      )}
      {dialog?.kind === "replan" && (
        <ReplanDialog
          sud={dialog.sud}
          firstOccupancy={dialog.occupancy}
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
          sude={sude}
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
