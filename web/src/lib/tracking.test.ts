import { expect, test } from "vitest";
import { AHEAD_S, FPS, TrackingBuffer, WINDOW_S, frameAt, interpolate, readPreference, writePreference } from "./tracking";
import type { Frame } from "../types";

const f = (t: number, players: Record<string, [number, number]>, ball: [number, number] = [50, 50]): Frame => ({
  t,
  ball,
  players,
});

test("interpolate is linear per player and keeps the newcomer", () => {
  const a = f(1, { p1: [0, 0], p2: [10, 10] }, [0, 0]);
  const b = f(2, { p1: [10, 20], p3: [5, 5] }, [10, 0]);
  const m = interpolate(a, b, 1.25);
  expect(m.t).toBe(1.25);
  expect(m.ball).toEqual([2.5, 0]);
  expect(m.players).toEqual({ p1: [2.5, 5], p3: [5, 5] });
  expect(interpolate(a, b, 2).players.p1).toEqual([10, 20]);
});

test("frameAt clamps to the ends and bisects", () => {
  const frames = [f(0, { p: [0, 0] }), f(0.25, { p: [1, 0] }), f(0.5, { p: [2, 0] })];
  expect(frameAt([], 1)).toBeNull();
  expect(frameAt(frames, -1)).toBe(frames[0]);
  expect(frameAt(frames, 9)).toBe(frames[2]);
  expect(frameAt(frames, 0.25)).toBe(frames[1]);
  expect(frameAt(frames, 0.375)!.players.p).toEqual([1.5, 0]);
});

test("buffer merges by t, prunes and plans the next window", () => {
  const b = new TrackingBuffer();
  expect(b.coverage()).toBeNull();
  expect(b.nextWindow(12.3)).toEqual([12.25, 12.25 + WINDOW_S]);
  b.add([f(0, {}), f(0.25, {})]);
  b.add([f(0.25, {}), f(0.5, {})]);
  expect(b.frames.map((x) => x.t)).toEqual([0, 0.25, 0.5]);
  expect(b.coverage()).toEqual({ from: 0, to: 0.5 });
  expect(b.nextWindow(0)).toEqual([0.75, 0.75 + WINDOW_S]);
  b.add(Array.from({ length: 400 }, (_, i) => f(0.75 + i / FPS, {})));
  expect(b.coverage()!.to).toBe(100.5);
  expect(b.nextWindow(0)).toBeNull(); // 100 s ahead is more than AHEAD_S
  expect(b.nextWindow(100.5 - AHEAD_S + 1)).toEqual([100.75, 100.75 + WINDOW_S]);
  expect(b.nextWindow(500)).toEqual([500, 500 + WINDOW_S]); // the clock jumped past the buffer
  b.prune(40);
  expect(b.coverage()!.from).toBe(40);
  expect(b.at(0.375)).toBeNull(); // pruned
  expect(b.at(45.1)!.t).toBe(45.1);
  b.markEnd();
  expect(b.nextWindow(20)).toBeNull(); // nextWindow stops after the end
});

test("preference round trip", () => {
  expect(readPreference(null, true)).toBe(true);
  expect(readPreference(null, false)).toBe(false);
  const store = new Map<string, string>();
  const s = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) } as unknown as Storage;
  writePreference(s, true);
  expect(readPreference(s, false)).toBe(true);
  writePreference(s, false);
  expect(readPreference(s, true)).toBe(false);
  expect(store.has("bts.tracking")).toBe(true);
});
