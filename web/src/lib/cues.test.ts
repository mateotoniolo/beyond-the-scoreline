import { expect, test } from "vitest";
import { activeCues, mergeCues } from "./cues";
import type { Cue } from "../types";

const cue = (id: string, layer: Cue["layer"], t: number, d: number): Cue => ({
  cue_id: id,
  t_start: t,
  duration_s: d,
  layer,
  text: id,
  lang: "en",
  profile: "analyst",
  moment_id: "m",
});

test("activeCues picks one cue per layer, latest start wins", () => {
  const cues = [
    cue("a", "lower_third", 10, 8),
    cue("b", "lower_third", 12, 8),
    cue("c", "side_panel", 10, 20),
  ];
  expect(activeCues(cues, 13).map((c) => c.cue_id)).toEqual(["b", "c"]);
  expect(activeCues(cues, 9)).toEqual([]);
  expect(activeCues(cues, 21).map((c) => c.cue_id)).toEqual(["c"]);
});

test("activeCues keeps a cue for duration_s real seconds at higher playback speeds", () => {
  const cues = [cue("a", "lower_third", 10, 8)];
  expect(activeCues(cues, 100, 30).map((c) => c.cue_id)).toEqual(["a"]);
  expect(activeCues(cues, 251, 30)).toEqual([]);
});

test("a cue that arrives late is shown from its arrival clock, not from t_start", () => {
  const late = { ...cue("a", "lower_third", 10, 8), shown_from: 400 };
  expect(activeCues([late], 100, 30)).toEqual([]);
  expect(activeCues([late], 401, 30).map((c) => c.cue_id)).toEqual(["a"]);
  expect(activeCues([late], 400 + 8 * 30 + 1, 30)).toEqual([]);
});

test("mergeCues anchors new cues at the current clock and keeps the anchor of replaced ones", () => {
  const first = mergeCues([], [cue("a", "lower_third", 10, 8)], 50);
  expect(first[0].shown_from).toBe(50);
  const cut = mergeCues(first, [cue("a", "lower_third", 10, 3), cue("b", "lower_third", 60, 8)], 70);
  expect(cut.find((c) => c.cue_id === "a")).toMatchObject({ duration_s: 3, shown_from: 50 });
  expect(cut.find((c) => c.cue_id === "b")?.shown_from).toBe(70);
  expect(cut).toHaveLength(2);
});
