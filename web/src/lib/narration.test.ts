import { expect, test } from "vitest";
import { LABELS, NarrationQueue, STALE_MS, htmlAudioPlayer, readPreference, writePreference, type Player } from "./narration";

class FakePlayer implements Player {
  played: string[] = [];
  stopped = 0;
  private settle: { resolve: () => void; reject: (e: Error) => void } | null = null;
  play(url: string): Promise<void> {
    this.played.push(url);
    return new Promise<void>((resolve, reject) => (this.settle = { resolve, reject }));
  }
  stop(): void {
    this.stopped++;
    this.end();
  }
  end(): void {
    const s = this.settle;
    this.settle = null;
    s?.resolve();
  }
  fail(): void {
    const s = this.settle;
    this.settle = null;
    s?.reject(new Error("503"));
  }
}

const flush = () => new Promise((r) => setTimeout(r, 0));

test("plays one clip at a time, in arrival order", async () => {
  const p = new FakePlayer();
  const q = new NarrationQueue(p);
  q.setEnabled(true);
  expect(q.enqueue("a", "/a")).toBe(true);
  expect(q.enqueue("b", "/b")).toBe(true);
  expect(p.played).toEqual(["/a"]);
  expect(q.playing).toBe("a");
  expect(q.pending).toBe(1);
  p.end();
  await flush();
  expect(p.played).toEqual(["/a", "/b"]);
  expect(q.playing).toBe("b");
  p.end();
  await flush();
  expect(q.playing).toBeNull();
  expect(q.pending).toBe(0);
});

test("plays each key once and ignores enqueues while off", async () => {
  const p = new FakePlayer();
  const q = new NarrationQueue(p);
  expect(q.enabled).toBe(false);
  expect(q.enqueue("a", "/a")).toBe(false);
  q.setEnabled(true);
  expect(q.enqueue("a", "/a")).toBe(true);
  expect(q.enqueue("a", "/a")).toBe(false);
  p.end();
  await flush();
  expect(q.enqueue("a", "/a")).toBe(false);
  expect(p.played).toEqual(["/a"]);
});

test("skips a clip whose turn comes more than 60 s after it was queued", async () => {
  let now = 0;
  const p = new FakePlayer();
  const q = new NarrationQueue(p, () => now);
  q.setEnabled(true);
  q.enqueue("a", "/a");
  q.enqueue("b", "/b");
  now = STALE_MS + 1;
  q.enqueue("c", "/c");
  p.end();
  await flush();
  expect(p.played).toEqual(["/a", "/c"]);
});

test("a failed clip does not block the next", async () => {
  const p = new FakePlayer();
  const q = new NarrationQueue(p);
  q.setEnabled(true);
  q.enqueue("a", "/a");
  q.enqueue("b", "/b");
  p.fail();
  await flush();
  expect(p.played).toEqual(["/a", "/b"]);
});

test("switching off stops the current clip and drops the rest", () => {
  const p = new FakePlayer();
  const q = new NarrationQueue(p);
  q.setEnabled(true);
  q.enqueue("a", "/a");
  q.enqueue("b", "/b");
  q.setEnabled(false);
  expect(p.stopped).toBe(1);
  expect(q.pending).toBe(0);
  expect(q.playing).toBeNull();
  expect(q.enqueue("c", "/c")).toBe(false);
  expect(p.played).toEqual(["/a"]);
});

test("mark records a key without playing; reset forgets everything", () => {
  const p = new FakePlayer();
  const q = new NarrationQueue(p);
  q.setEnabled(true);
  q.mark("a");
  expect(q.enqueue("a", "/a")).toBe(false);
  expect(p.played).toEqual([]);
  q.reset();
  expect(q.enqueue("a", "/a")).toBe(true);
  expect(q.enabled).toBe(true);
});

test("preference round trip and a full label set per language", () => {
  expect(readPreference(null)).toBe(false);
  const store = new Map<string, string>();
  const s = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
  };
  expect(readPreference(s)).toBe(false);
  writePreference(s, true);
  expect(readPreference(s)).toBe(true);
  writePreference(s, false);
  expect(readPreference(s)).toBe(false);
  for (const lang of ["en", "es"] as const) {
    expect(Object.keys(LABELS[lang]).sort()).toEqual(["listen", "stop", "toggle", "unavailable"]);
  }
  expect(LABELS.en.toggle).toBe("Narration");
  expect(LABELS.es.toggle).toBe("Narración");
});

class FakeAudio extends EventTarget {
  src = "";
  paused = true;
  preload = "";
  /** One entry per play() call, so a test can reject an earlier call after a later one started. */
  pending: { resolve: () => void; reject: (e: Error) => void }[] = [];
  play(): Promise<void> {
    this.paused = false;
    return new Promise<void>((resolve, reject) => this.pending.push({ resolve, reject }));
  }
  pause(): void {
    this.paused = true;
  }
  removeAttribute(): void {
    this.src = "";
  }
}

test("a late rejection of a failed clip's play() does not settle the next clip", async () => {
  const created: FakeAudio[] = [];
  (globalThis as unknown as { Audio: unknown }).Audio = class extends FakeAudio {
    constructor() {
      super();
      created.push(this);
    }
  };
  const player = htmlAudioPlayer();
  const first = player.play("/first");
  const el = created[0];
  el.dispatchEvent(new Event("error")); // the browser reports the failed load first
  await first;
  let secondDone = false;
  const second = player.play("/second").then(() => {
    secondDone = true;
  });
  el.pending[0].reject(new DOMException("NotSupportedError", "NotSupportedError")); // then rejects /first
  await flush();
  expect(secondDone).toBe(false);
  el.dispatchEvent(new Event("ended"));
  await second;
  expect(secondDone).toBe(true);
});
