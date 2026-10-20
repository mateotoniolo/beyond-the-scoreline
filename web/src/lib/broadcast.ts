import type { Lang, Profile } from "../types";

/** The program output is designed at this size and scaled to the viewport with one transform. */
export const STAGE = { width: 1280, height: 720 } as const;
export const BROADCAST_PREFIX = "#/broadcast";

export interface BroadcastParams {
  match: string | null;
  profile: Profile;
  lang: Lang;
  /** Narration starts only after a click on the stage (autoplay rules); off by default. */
  narration: boolean;
  /** The tracking layer; on by default on the program output. */
  tracking: boolean;
}

export function isBroadcastHash(hash: string): boolean {
  return hash === BROADCAST_PREFIX || hash.startsWith(`${BROADCAST_PREFIX}?`);
}

/** `#/broadcast?match=&profile=&lang=&narration=&tracking=`; unknown values fall back to the defaults. */
export function parseBroadcastHash(hash: string): BroadcastParams {
  const at = hash.indexOf("?");
  const params = new URLSearchParams(at === -1 ? "" : hash.slice(at + 1));
  const flag = (key: string, fallback: boolean) => {
    const value = params.get(key);
    return value === null ? fallback : value === "1" || value === "true";
  };
  return {
    match: params.get("match") || null,
    profile: params.get("profile") === "fan" ? "fan" : "analyst",
    lang: params.get("lang") === "es" ? "es" : "en",
    narration: flag("narration", false),
    tracking: flag("tracking", true),
  };
}

export function broadcastUrl(matchId: string, profile: Profile, lang: Lang): string {
  return `${BROADCAST_PREFIX}?match=${encodeURIComponent(matchId)}&profile=${profile}&lang=${lang}`;
}

/** The factor that fits the 1280×720 stage inside a viewport on both axes. */
export function stageScale(vw: number, vh: number): number {
  return Math.min(vw / STAGE.width, vh / STAGE.height);
}
