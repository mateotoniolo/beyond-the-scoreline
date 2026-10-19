import { expect, test } from "vitest";
import { activeCues } from "./cues";
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
