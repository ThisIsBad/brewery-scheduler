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
  globalSudLabel,
  sudNumberLabel,
} from "../domain";
import { ReplanDialog } from "./ReplanDialog";
import { ScheduleDialog } from "./ScheduleDialog";
import { TankWithdrawDialog } from "./TankWithdrawDialog";
import { TransferDialog } from "./TransferDialog";
import { WithdrawDialog } from "./WithdrawDialog";

interface KellerblickProps {
  tanks: Tank[];
  sude: Sud[];
  onChanged: (sud: Sud) => void;
}

type DialogState =
  | { kind: "transfer"; sud: Sud; occupancy: Occupancy }
  | {
      kind: "withdraw";
      sud: Sud;
      occupancy: Occupancy;
      withdrawalKind: WithdrawalKind;
    }
  | {
      kind: "tankWithdraw";
      tank: Tank;
      entries: { sud: Sud; occ: Occupancy }[];
      withdrawalKind: WithdrawalKind;
    }
  | { kind: "replan"; sud: Sud; occupancy: Occupancy }
  | { kind: "schedule"; sud: Sud }
  | null;

export function Kellerblick({ tanks, sude, onChanged }: KellerblickProps) {
  const [dialog, setDialog] = useState<DialogState>(null);
  // Gemischte Ausschank-Karte: nur „Ausgeschenkt" ist direkt sichtbar,
  // Fass/Schwund stecken hinter „Mehr" (Stefan, 2026-08-06).
  const [mehrTank, setMehrTank] = useState<string | null>(null);
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
  // Finished batches (auto-completed at share 0, or discarded) are done —
  // they leave the Kellerblick instead of nagging as overdue.
  const overdue = leads
    .filter(
      (sud) =>
        sud.occupancies.length > 0 &&
        sud.status !== "served" &&
        sud.status !== "discarded" &&
        occupancyAt(sud, now) === null &&
        firstFutureOccupancy(sud, now) === null,
    )
    .map((sud) => ({
      sud,
      occ: sud.occupancies.reduce((latest, o) =>
        new Date(o.start_at) > new Date(latest.start_at) ? o : latest,
      ),
    }));

  // Blending (2026-08-04): an Ausschank tank mixes batches, so it gets ONE
  // card listing its contents; kegs, pours and Schwund are booked on the
  // tank and distributed server-side. Other stages keep per-Sud cards.
  const ausschankByTank = new Map<string, { sud: Sud; occ: Occupancy }[]>();
  for (const entry of current) {
    if (entry.occ.stage !== "ausschank") continue;
    const list = ausschankByTank.get(entry.occ.tank_id) ?? [];
    list.push(entry);
    ausschankByTank.set(entry.occ.tank_id, list);
  }

  return (
    <div className="kellerblick">
      <section>
        <h2>Jetzt im Keller</h2>
        {current.length === 0 && <p className="empty">Kein Tank belegt.</p>}
        {[...ausschankByTank.entries()].map(([tankId, entries]) => {
          const tank = tankById.get(tankId);
          const withRemaining = entries.map((e) => ({
            ...e,
            remaining: remainingHl(e.sud, sude, e.occ),
          }));
          const total = withRemaining.reduce((sum, e) => sum + e.remaining, 0);
          const warnings = [
            ...new Set(entries.flatMap(({ sud }) => sud.warnings ?? [])),
          ];
          return (
            <article
              className={warnings.length > 0 ? "card warn" : "card"}
              key={tankId}
            >
              <header>
                <strong>{tank?.name ?? "?"}</strong>
                <span className="muted">
                  {tank ? formatHl(tank.capacity_hl) : ""} · Ausschank
                </span>
              </header>
              <div className="card-body">
                {withRemaining.map(({ sud, occ, remaining }) => (
                  <div className="beer" key={occ.id}>
                    {sudNumberLabel(sud, sude)} · {sud.recipe.name}{" "}
                    <span className="muted">({globalSudLabel(sud, sude)})</span>{" "}
                    · noch {formatHl(remaining)}
                    {/* Vermischt ist vermischt (Stefan, 2026-08-06): sobald
                        mehrere Sude im Tank sind, gibt es kein Aufteilen
                        mehr — Umdrücken nur solange der Sud allein ist. */}
                    {entries.length === 1 && (
                      <>
                        {" "}
                        <button
                          type="button"
                          className="secondary"
                          onClick={() =>
                            setDialog({ kind: "transfer", sud, occupancy: occ })
                          }
                        >
                          Umdrücken
                        </button>
                      </>
                    )}
                  </div>
                ))}
                {entries.length > 1 && (
                  <div className="muted">Zusammen noch {formatHl(total)}</div>
                )}
                {warnings.length > 0 && (
                  <div className="warn-note">⚠️ {warnings.join(" · ")}</div>
                )}
              </div>
              <footer>
                {entries.length > 1 ? (
                  <>
                    <button
                      type="button"
                      disabled={total <= 0}
                      onClick={() =>
                        setDialog({
                          kind: "tankWithdraw",
                          tank: tank!,
                          entries,
                          withdrawalKind: "ausschank",
                        })
                      }
                    >
                      Ausgeschenkt
                    </button>
                    {mehrTank === tankId && (
                      <>
                        <button
                          type="button"
                          className="secondary"
                          disabled={total <= 0}
                          onClick={() =>
                            setDialog({
                              kind: "tankWithdraw",
                              tank: tank!,
                              entries,
                              withdrawalKind: "keg_fill",
                            })
                          }
                        >
                          Fass abfüllen
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          disabled={total <= 0}
                          onClick={() =>
                            setDialog({
                              kind: "tankWithdraw",
                              tank: tank!,
                              entries,
                              withdrawalKind: "schwund",
                            })
                          }
                        >
                          Schwund
                        </button>
                      </>
                    )}
                    <button
                      type="button"
                      className="secondary"
                      onClick={() =>
                        setMehrTank(mehrTank === tankId ? null : tankId)
                      }
                    >
                      {mehrTank === tankId ? "Weniger" : "Mehr"}
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      disabled={total <= 0}
                      onClick={() =>
                        setDialog({
                          kind: "tankWithdraw",
                          tank: tank!,
                          entries,
                          withdrawalKind: "keg_fill",
                        })
                      }
                    >
                      Fass abfüllen
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={total <= 0}
                      onClick={() =>
                        setDialog({
                          kind: "tankWithdraw",
                          tank: tank!,
                          entries,
                          withdrawalKind: "ausschank",
                        })
                      }
                    >
                      Ausgeschenkt
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={total <= 0}
                      onClick={() =>
                        setDialog({
                          kind: "tankWithdraw",
                          tank: tank!,
                          entries,
                          withdrawalKind: "schwund",
                        })
                      }
                    >
                      Schwund
                    </button>
                  </>
                )}
              </footer>
            </article>
          );
        })}
        {current
          .filter(({ occ }) => occ.stage !== "ausschank")
          .map(({ sud, occ }) => {
            const tank = tankById.get(occ.tank_id);
            const remaining = remainingHl(sud, sude, occ);
            const warnings = sud.warnings ?? [];
            return (
              <article
                className={warnings.length > 0 ? "card warn" : "card"}
                key={occ.id}
              >
                <header>
                  <strong>{tank?.name ?? "?"}</strong>
                  <span className="muted">
                    {tank ? formatHl(tank.capacity_hl) : ""} ·{" "}
                    {STAGE_LABEL[occ.stage]}
                  </span>
                </header>
                <div className="card-body">
                  <div className="beer">
                    {sudNumberLabel(sud, sude)} · {sud.recipe.name}{" "}
                    <span className="muted">({globalSudLabel(sud, sude)})</span>
                  </div>
                  <div className="muted">
                    {dayProgressLabel(occ, now)} im Tank
                    {occ.end_at ? ` · bis ${formatDate(occ.end_at)}` : ""}
                    {" · "}noch {formatHl(remaining)}
                  </div>
                  <div className="muted">
                    {ageLabel(sud, now)}
                    {sud.recipe_overrides &&
                      Object.keys(sud.recipe_overrides).length > 0 &&
                      " · abweichende Rezeptzeiten"}
                  </div>
                  {warnings.length > 0 && (
                    <div className="warn-note">⚠️ {warnings.join(" · ")}</div>
                  )}
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
            const warnings = sud.warnings ?? [];
            return (
              <article
                className={
                  warnings.length > 0 ? "card overdue warn" : "card overdue"
                }
                key={occ.id}
              >
                <header>
                  <strong>{tank?.name ?? "?"}</strong>
                  <span className="muted">{STAGE_LABEL[occ.stage]}</span>
                </header>
                <div className="card-body">
                  <div className="beer">
                    {sudNumberLabel(sud, sude)} · {sud.recipe.name}{" "}
                    <span className="muted">({globalSudLabel(sud, sude)})</span>
                  </div>
                  <div className="muted">
                    geplantes Ende {occ.end_at ? formatDate(occ.end_at) : "—"}{" "}
                    ist vorbei — Bier steht noch im Tank
                  </div>
                  {warnings.length > 0 && (
                    <div className="warn-note">⚠️ {warnings.join(" · ")}</div>
                  )}
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
            const warnings = sud.warnings ?? [];
            return (
              <article
                className={
                  warnings.length > 0 ? "card planned warn" : "card planned"
                }
                key={occ.id}
              >
                <div className="card-body">
                  <div className="beer">
                    {sudNumberLabel(sud, sude)} · {sud.recipe.name}{" "}
                    <span className="muted">({globalSudLabel(sud, sude)})</span>
                  </div>
                  <div className="muted">
                    ab {formatDate(occ.start_at)} in {tank?.name ?? "?"} (
                    {STAGE_LABEL[occ.stage]})
                  </div>
                  {warnings.length > 0 && (
                    <div className="warn-note">⚠️ {warnings.join(" · ")}</div>
                  )}
                </div>
                <footer>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() =>
                      setDialog({ kind: "replan", sud, occupancy: occ })
                    }
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
                  {sudNumberLabel(sud, sude)} · {sud.recipe.name}{" "}
                  <span className="muted">({globalSudLabel(sud, sude)})</span>
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
      {dialog?.kind === "tankWithdraw" && (
        <TankWithdrawDialog
          tank={dialog.tank}
          entries={dialog.entries}
          sude={sude}
          kind={dialog.withdrawalKind}
          onClose={() => setDialog(null)}
          onDone={(updated) => {
            updated.forEach(onChanged);
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
