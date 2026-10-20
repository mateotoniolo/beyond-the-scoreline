import type { MatchEvent } from "../types";

/**
 * Who has the ball after each event, mirroring `bts.tracking.possession` so the pitch draws
 * defensive events (a save, an interception) in the same frame the tracker uses. Events are
 * recorded in the attacking frame of the side in possession; on-ball events in their own.
 */
export const ON_BALL = new Set(["pass", "carry", "shot", "miscontrol", "ball_out"]);
const TAKES_THE_BALL = new Set(["interception", "recovery", "clearance", "goalkeeper"]);

const other = (team: string, homeId: string, awayId: string) => (team === homeId ? awayId : homeId);

export function possessionAfter(e: MatchEvent, holder: string, homeId: string, awayId: string): string {
  switch (e.type) {
    case "period_start":
    case "pass":
    case "carry":
      return e.team_id;
    case "ball_out":
    case "miscontrol":
      return other(e.team_id, homeId, awayId);
    case "shot":
      return e.outcome === "goal" || e.outcome === "off_target" ? other(e.team_id, homeId, awayId) : e.team_id;
    case "duel":
      return e.outcome === "success" ? e.team_id : holder;
    default:
      return TAKES_THE_BALL.has(e.type) ? e.team_id : holder;
  }
}

/** Event id → the team whose attacking frame its coordinates are in; the home side holds first. */
export function frameTeams(events: readonly MatchEvent[], homeId: string, awayId: string): Map<number, string> {
  const frames = new Map<number, string>();
  let holder = homeId;
  for (const e of events) {
    frames.set(e.event_id, ON_BALL.has(e.type) ? e.team_id : holder);
    holder = possessionAfter(e, holder, homeId, awayId);
  }
  return frames;
}
