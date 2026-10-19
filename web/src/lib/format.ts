import type { Lang, MatchEvent, MatchMeta } from "../types";

export const clockOf = (seconds: number) => {
  const total = Math.floor(seconds);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
};

export const teamOf = (meta: MatchMeta, teamId: string) =>
  meta.home.team_id === teamId ? meta.home : meta.away;

export const playerName = (meta: MatchMeta, playerId: string | null) => {
  if (!playerId) return "";
  const all = [...meta.home.players, ...meta.away.players];
  return all.find((p) => p.player_id === playerId)?.name ?? playerId;
};

const VERBS: Record<Lang, Record<string, string>> = {
  en: {
    pass: "pass",
    carry: "carry",
    shot: "shot",
    duel: "tackle",
    interception: "interception",
    clearance: "clearance",
    recovery: "recovery",
    miscontrol: "loses control",
    ball_out: "ball out",
    foul: "foul",
    goalkeeper: "save",
    pressure: "press",
    substitution: "substitution",
    card: "card",
    period_start: "kick-off",
    period_end: "whistle",
  },
  es: {
    pass: "pase",
    carry: "conducción",
    shot: "remate",
    duel: "entrada",
    interception: "intercepción",
    clearance: "despeje",
    recovery: "recuperación",
    miscontrol: "pierde el control",
    ball_out: "pelota afuera",
    foul: "falta",
    goalkeeper: "atajada",
    pressure: "presión",
    substitution: "cambio",
    card: "tarjeta",
    period_start: "saque inicial",
    period_end: "pitazo",
  },
};

const OUTCOMES: Record<Lang, Record<string, string>> = {
  en: { fail: "lost", saved: "saved", blocked: "blocked", off_target: "off target" },
  es: { fail: "perdido", saved: "atajado", blocked: "bloqueado", off_target: "desviado" },
};
const SKIP_SUBTYPES = new Set(["short", "open_play", "save", "tackle"]);

export function describe(e: MatchEvent, lang: Lang): string {
  const verb = VERBS[lang][e.type] ?? e.type;
  if (e.type === "shot" && e.outcome === "goal") return lang === "en" ? "GOAL" : "GOL";
  const bits = [verb];
  if (e.subtype && !SKIP_SUBTYPES.has(e.subtype) && e.type !== "period_start" && e.type !== "period_end") {
    bits.push(e.subtype);
  }
  if (e.outcome && e.outcome !== "success") bits.push(OUTCOMES[lang][e.outcome] ?? e.outcome);
  return bits.join(" ");
}
