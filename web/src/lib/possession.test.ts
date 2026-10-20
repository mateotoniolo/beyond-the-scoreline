import { expect, test } from "vitest";
import { frameTeams, possessionAfter } from "./possession";
import type { MatchEvent } from "../types";

const ev = (id: number, type: string, team: string, outcome: string | null = null): MatchEvent => ({
  event_id: id,
  match_id: "m",
  period: 1,
  t: id,
  clock: "",
  team_id: team,
  player_id: null,
  type,
  subtype: null,
  start: { x: 1, y: 1 },
  end: null,
  outcome,
  tags: [],
  meta: {},
});

test("possession follows the tracker's rule", () => {
  expect(possessionAfter(ev(1, "pass", "t2", "fail"), "t1", "t1", "t2")).toBe("t2");
  expect(possessionAfter(ev(1, "ball_out", "t1", "fail"), "t1", "t1", "t2")).toBe("t2");
  expect(possessionAfter(ev(1, "miscontrol", "t1", "fail"), "t1", "t1", "t2")).toBe("t2");
  expect(possessionAfter(ev(1, "shot", "t1", "saved"), "t1", "t1", "t2")).toBe("t1");
  expect(possessionAfter(ev(1, "shot", "t1", "blocked"), "t1", "t1", "t2")).toBe("t1");
  expect(possessionAfter(ev(1, "shot", "t1", "off_target"), "t1", "t1", "t2")).toBe("t2");
  expect(possessionAfter(ev(1, "shot", "t1", "goal"), "t1", "t1", "t2")).toBe("t2");
  expect(possessionAfter(ev(1, "goalkeeper", "t2", "success"), "t1", "t1", "t2")).toBe("t2");
  expect(possessionAfter(ev(1, "clearance", "t2", "success"), "t1", "t1", "t2")).toBe("t2");
  expect(possessionAfter(ev(1, "duel", "t2", "success"), "t1", "t1", "t2")).toBe("t2");
  expect(possessionAfter(ev(1, "duel", "t2", "fail"), "t1", "t1", "t2")).toBe("t1");
  expect(possessionAfter(ev(1, "pressure", "t2"), "t1", "t1", "t2")).toBe("t1");
  expect(possessionAfter(ev(1, "period_start", "t2"), "t1", "t1", "t2")).toBe("t2");
});

test("frameTeams places defensive events in the holder's frame", () => {
  const events = [
    ev(1, "pass", "t1", "fail"),
    ev(2, "interception", "t2", "success"),
    ev(3, "pass", "t2", "success"),
    ev(4, "shot", "t2", "saved"),
    ev(5, "goalkeeper", "t1", "success"),
    ev(6, "ball_out", "t1", "fail"),
    ev(7, "pressure", "t1"),
  ];
  const frames = frameTeams(events, "t1", "t2");
  expect([...frames.values()]).toEqual(["t1", "t1", "t2", "t2", "t2", "t1", "t2"]);
  expect(frames.get(7)).toBe("t2");
});
