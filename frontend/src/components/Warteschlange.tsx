import { useSyncExternalStore } from "react";

import {
  discardConflict,
  getSnapshot,
  replay,
  subscribe,
} from "../api/queue";
import { formatDate } from "../domain";

interface WarteschlangeProps {
  /** Nach erfolgreichem Nachsenden die Daten neu laden. */
  onReplayed: () => void;
}

/** Sichtbarer Status der Offline-Warteschlange (issue #10): was noch auf
 * Netz wartet und was der Server beim Nachsenden abgelehnt hat. Ohne
 * Einträge rendert die Leiste nichts. */
export function Warteschlange({ onReplayed }: WarteschlangeProps) {
  const { pending, conflicts } = useSyncExternalStore(subscribe, getSnapshot);

  if (pending.length === 0 && conflicts.length === 0) return null;

  const send = async () => {
    if (await replay()) onReplayed();
  };

  return (
    <div className="queue banner" role="status">
      {pending.length > 0 && (
        <div className="queue-pending">
          <span>
            📶 {pending.length === 1 ? "1 Buchung wartet" : `${pending.length} Buchungen warten`}{" "}
            auf Netz ({pending.map((p) => p.label).join(" · ")})
          </span>
          <button type="button" onClick={() => void send()}>
            Jetzt senden
          </button>
        </div>
      )}
      {conflicts.map((c) => (
        <div className="queue-conflict" key={c.id}>
          <span>
            ⚠️ {c.label} vom {formatDate(c.queuedAt)} wurde abgelehnt: {c.reason}
          </span>
          <button type="button" onClick={() => discardConflict(c.id)}>
            Verwerfen
          </button>
        </div>
      ))}
    </div>
  );
}
