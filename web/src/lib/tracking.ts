import type { Frame } from "../types";

/** Frames per match second served by the API. */
export const FPS = 4;
/** Match seconds asked for per request (the API caps a call at 600 frames). */
export const WINDOW_S = 150;
/** Fetch the next window when fewer match seconds than this remain ahead of the clock. */
export const AHEAD_S = 90;
/** Frames older than this behind the clock are dropped. */
export const KEEP_BEHIND_S = 30;
export const STORAGE_KEY = "bts.tracking";

const grid = (t: number) => Math.floor(t * FPS + 1e-9) / FPS;
const lerp = (a: number, b: number, f: number) => a + (b - a) * f;

/**
 * The frame at `t` between `a` and `b` (a.t <= t <= b.t), linear per player. A player only in
 * `b` has just come on and takes `b`'s position; one only in `a` has gone off and is dropped.
 */
export function interpolate(a: Frame, b: Frame, t: number): Frame {
  const span = b.t - a.t;
  const f = span <= 0 ? 1 : Math.min(1, Math.max(0, (t - a.t) / span));
  const players: Frame["players"] = {};
  for (const [pid, to] of Object.entries(b.players)) {
    const from = a.players[pid];
    players[pid] = from ? [lerp(from[0], to[0], f), lerp(from[1], to[1], f)] : to;
  }
  return { t, ball: [lerp(a.ball[0], b.ball[0], f), lerp(a.ball[1], b.ball[1], f)], players };
}

/** The (interpolated) frame at `t`; clamped to the first and last frames, null when empty. */
export function frameAt(frames: readonly Frame[], t: number): Frame | null {
  if (frames.length === 0) return null;
  if (t <= frames[0].t) return frames[0];
  const last = frames[frames.length - 1];
  if (t >= last.t) return last;
  let lo = 0;
  let hi = frames.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (frames[mid].t <= t) lo = mid;
    else hi = mid;
  }
  if (frames[lo].t === t) return frames[lo];
  return interpolate(frames[lo], frames[hi], t);
}

/** Frames sorted by `t`, fetched in windows ahead of the clock. */
export class TrackingBuffer {
  private items: Frame[] = [];
  private ended = false;

  get frames(): readonly Frame[] {
    return this.items;
  }

  /** Merge by `t`: a frame already held is replaced, the rest keep the list sorted. */
  add(frames: Frame[]): void {
    if (frames.length === 0) return;
    const byT = new Map(this.items.map((f) => [f.t, f]));
    for (const f of frames) byT.set(f.t, f);
    this.items = [...byT.values()].sort((a, b) => a.t - b.t);
  }

  coverage(): { from: number; to: number } | null {
    if (this.items.length === 0) return null;
    return { from: this.items[0].t, to: this.items[this.items.length - 1].t };
  }

  prune(before: number): void {
    const first = this.items.findIndex((f) => f.t >= before);
    if (first > 0) this.items = this.items.slice(first);
    else if (first === -1 && this.items.length) this.items = this.items.slice(-1);
  }

  /** The API answered past full time: nothing more to ask for. */
  markEnd(): void {
    this.ended = true;
  }

  /** `[from, to]` of the next window to fetch, or null while enough lies ahead of `clock`. */
  nextWindow(clock: number, aheadS = AHEAD_S): [number, number] | null {
    if (this.ended) return null;
    const cover = this.coverage();
    let from: number;
    if (cover === null || cover.to < clock) from = grid(clock);
    else if (cover.to - clock >= aheadS) return null;
    else from = cover.to + 1 / FPS;
    return [from, from + WINDOW_S];
  }

  at(t: number): Frame | null {
    const cover = this.coverage();
    if (cover === null || t < cover.from) return null;
    return frameAt(this.items, t);
  }
}

export function readPreference(storage: Storage | null, fallback: boolean): boolean {
  try {
    const raw = storage?.getItem(STORAGE_KEY);
    return raw === null || raw === undefined ? fallback : raw === "1";
  } catch {
    return fallback;
  }
}

export function writePreference(storage: Storage | null, on: boolean): void {
  try {
    storage?.setItem(STORAGE_KEY, on ? "1" : "0");
  } catch {
    // private mode or a full store: the switch still works for this page
  }
}
