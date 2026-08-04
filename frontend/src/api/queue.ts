// Offline-Warteschlange (issue #10): der Keller hat Funklöcher, Buchungen
// dürfen trotzdem nie verloren gehen. Mutationen, die das Netz gar nicht
// erreichen, landen hier (localStorage), werden bei Rückkehr des Netzes in
// Reihenfolge nachgesendet und tauchen bei Ablehnung (409/422 — z. B. weil
// inzwischen jemand anderes gebucht hat) sichtbar als Konflikt auf.
//
// Bewusst OHNE Workbox Background Sync und ohne Query-Bibliothek: die App
// spricht direkt fetch, also ist eine ~100-Zeilen-Warteschlange die Lösung
// mit den wenigsten beweglichen Teilen (CLAUDE.md). Grenze der v1: ein
// Request, der den Server erreicht, dessen Antwort aber im Funkloch
// verloren geht, wird NICHT erneut gesendet (sonst Doppelbuchung) — der
// Eintrag landet als Konflikt zur manuellen Prüfung.

export interface QueuedMutation {
  id: string;
  path: string;
  method: string;
  body: string | null;
  /** Deutsche Kurzbeschreibung für die Statusleiste. */
  label: string;
  queuedAt: string;
}

export interface QueueConflict extends QueuedMutation {
  /** Die Server-Antwort (detail) oder der Transportfehler. */
  reason: string;
}

const QUEUE_KEY = "keller-warteschlange";
const CONFLICT_KEY = "keller-konflikte";

/** Wirft der Client, wenn eine Buchung mangels Netz eingereiht wurde. */
export class QueuedError extends Error {
  queued = true;
  constructor(label: string) {
    super(
      `Kein Netz — „${label}“ ist gespeichert und wird automatisch ` +
        "gesendet, sobald Verbindung besteht.",
    );
  }
}

function read<T>(key: string): T[] {
  try {
    return JSON.parse(localStorage.getItem(key) ?? "[]") as T[];
  } catch {
    return [];
  }
}

function write(key: string, value: unknown[]): void {
  localStorage.setItem(key, JSON.stringify(value));
  for (const listener of listeners) listener();
}

const listeners = new Set<() => void>();

/** React-Anbindung (useSyncExternalStore). */
export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function pending(): QueuedMutation[] {
  return read<QueuedMutation>(QUEUE_KEY);
}

export function conflicts(): QueueConflict[] {
  return read<QueueConflict>(CONFLICT_KEY);
}

// Snapshots für useSyncExternalStore müssen referenzstabil sein, solange
// sich nichts geändert hat — sonst rendert React endlos.
let snapshot = { pending: pending(), conflicts: conflicts() };

export function getSnapshot(): { pending: QueuedMutation[]; conflicts: QueueConflict[] } {
  const fresh = { pending: pending(), conflicts: conflicts() };
  if (
    JSON.stringify(fresh.pending) !== JSON.stringify(snapshot.pending) ||
    JSON.stringify(fresh.conflicts) !== JSON.stringify(snapshot.conflicts)
  ) {
    snapshot = fresh;
  }
  return snapshot;
}

/** Deutsche Beschriftung aus dem API-Pfad — hält die Aufrufer unverändert. */
export function labelFor(path: string, method: string): string {
  if (path.includes("/transfer")) return "Umdrücken";
  if (path.includes("/withdraw") && path.includes("/tanks/")) return "Tank-Buchung";
  if (path.includes("/withdraw")) return "Buchung (Fass/Ausschank)";
  if (path.includes("/schedule")) return "Planänderung";
  if (path.includes("/sude")) return "Neuer Sud";
  if (path.includes("/recipes")) return "Rezeptänderung";
  if (path.includes("/tanks") || path.includes("/locations"))
    return method === "DELETE" ? "Stammdaten löschen" : "Stammdatenänderung";
  return "Buchung";
}

export function enqueue(path: string, init: RequestInit): QueuedMutation {
  const entry: QueuedMutation = {
    id: crypto.randomUUID(),
    path,
    method: init.method ?? "POST",
    body: typeof init.body === "string" ? init.body : null,
    label: labelFor(path, init.method ?? "POST"),
    queuedAt: new Date().toISOString(),
  };
  write(QUEUE_KEY, [...pending(), entry]);
  return entry;
}

export function discardConflict(id: string): void {
  write(
    CONFLICT_KEY,
    conflicts().filter((c) => c.id !== id),
  );
}

let replaying = false;

/** Sendet die Warteschlange in Reihenfolge nach. Stoppt beim ersten
 * Netzfehler (weiter offline); Server-Ablehnungen wandern in die
 * Konfliktliste, damit nichts stumm verschwindet. Liefert true, wenn
 * mindestens eine Buchung durchging (dann sollten die Daten neu geladen
 * werden). */
export async function replay(): Promise<boolean> {
  if (replaying) return false;
  replaying = true;
  let sentAny = false;
  try {
    let queue = pending();
    while (queue.length > 0) {
      const entry = queue[0];
      let res: Response;
      try {
        res = await fetch(entry.path, {
          method: entry.method,
          headers: { "Content-Type": "application/json" },
          body: entry.body,
        });
      } catch {
        break; // immer noch offline — Rest bleibt liegen
      }
      queue = queue.slice(1);
      write(QUEUE_KEY, queue);
      if (res.ok) {
        sentAny = true;
      } else {
        let reason = `${res.status} ${res.statusText}`;
        try {
          const parsed = JSON.parse(await res.text());
          if (typeof parsed.detail === "string") reason = parsed.detail;
        } catch {
          // Transporttext reicht
        }
        write(CONFLICT_KEY, [...conflicts(), { ...entry, reason }]);
      }
    }
  } finally {
    replaying = false;
  }
  return sentAny;
}
