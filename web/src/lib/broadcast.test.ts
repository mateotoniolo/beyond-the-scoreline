import { expect, test } from "vitest";
import { broadcastUrl, isBroadcastHash, parseBroadcastHash, stageScale } from "./broadcast";

test("hash parsing and url building round trip", () => {
  expect(isBroadcastHash("#/broadcast?match=11-abc")).toBe(true);
  expect(isBroadcastHash("#/broadcast")).toBe(true);
  expect(isBroadcastHash("#/other")).toBe(false);
  expect(isBroadcastHash("")).toBe(false);
  expect(parseBroadcastHash("#/broadcast?match=11-abc&profile=fan&lang=es&narration=1&tracking=0")).toEqual({
    match: "11-abc",
    profile: "fan",
    lang: "es",
    narration: true,
    tracking: false,
  });
  expect(parseBroadcastHash("#/broadcast?profile=coach&lang=fr")).toEqual({
    match: null,
    profile: "analyst",
    lang: "en",
    narration: false,
    tracking: true,
  });
  expect(parseBroadcastHash("#/broadcast?match=")).toEqual({ match: null, profile: "analyst", lang: "en", narration: false, tracking: true });
  expect(broadcastUrl("11-abc", "fan", "es")).toBe("#/broadcast?match=11-abc&profile=fan&lang=es");
  expect(parseBroadcastHash(broadcastUrl("11-abc", "fan", "es")).match).toBe("11-abc");
});

test("stage scale fits both axes", () => {
  expect(stageScale(1280, 720)).toBe(1);
  expect(stageScale(1920, 1080)).toBe(1.5);
  expect(stageScale(1920, 720)).toBe(1);
  expect(stageScale(640, 1080)).toBe(0.5);
});
