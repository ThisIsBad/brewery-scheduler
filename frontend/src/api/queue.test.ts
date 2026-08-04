import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { conflicts, enqueue, pending, replay } from "./queue";

const entry = (path: string, body: unknown) =>
  enqueue(path, { method: "POST", body: JSON.stringify(body) });

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

afterEach(() => {
  localStorage.clear();
});

describe("Offline-Warteschlange", () => {
  it("reiht Buchungen ein und beschriftet sie deutsch", () => {
    entry("/api/sude/abc/transfer", { allocations: [] });
    entry("/api/tanks/xyz/withdraw", { volume_hl: 3 });
    const q = pending();
    expect(q).toHaveLength(2);
    expect(q[0].label).toBe("Umdrücken");
    expect(q[1].label).toBe("Tank-Buchung");
  });

  it("sendet in Reihenfolge nach und leert die Schlange", async () => {
    entry("/api/sude/a/transfer", { a: 1 });
    entry("/api/sude/b/withdraw", { b: 2 });
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) => {
        calls.push(path);
        return new Response("{}", { status: 200 });
      }),
    );

    expect(await replay()).toBe(true);
    expect(calls).toEqual(["/api/sude/a/transfer", "/api/sude/b/withdraw"]);
    expect(pending()).toHaveLength(0);
    expect(conflicts()).toHaveLength(0);
  });

  it("stoppt beim Netzfehler und lässt den Rest liegen", async () => {
    entry("/api/sude/a/transfer", { a: 1 });
    entry("/api/sude/b/withdraw", { b: 2 });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("offline");
      }),
    );

    expect(await replay()).toBe(false);
    expect(pending()).toHaveLength(2);
    expect(conflicts()).toHaveLength(0);
  });

  it("macht Server-Ablehnungen als Konflikt sichtbar statt sie zu verlieren", async () => {
    entry("/api/sude/a/transfer", { a: 1 });
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: "Tank ist inzwischen belegt." }), {
            status: 409,
          }),
      ),
    );

    expect(await replay()).toBe(false);
    expect(pending()).toHaveLength(0);
    const c = conflicts();
    expect(c).toHaveLength(1);
    expect(c[0].reason).toBe("Tank ist inzwischen belegt.");
    expect(c[0].label).toBe("Umdrücken");
  });
});
