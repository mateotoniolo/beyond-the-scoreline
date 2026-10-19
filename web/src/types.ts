// Mirrors the pydantic models served by the FastAPI backend.

export type Profile = "analyst" | "fan";
export type Lang = "en" | "es";
export type Layer = "lower_third" | "side_panel" | "ticker";

export interface Point {
  x: number;
  y: number;
}

export interface MatchEvent {
  event_id: number;
  match_id: string;
  period: 1 | 2;
  t: number;
  clock: string;
  team_id: string;
  player_id: string | null;
  type: string;
  subtype: string | null;
  start: Point;
  end: Point | null;
  outcome: string | null;
  tags: string[];
  meta: Record<string, number | string | boolean>;
}

export interface Player {
  player_id: string;
  name: string;
  team_id: string;
  position: "GK" | "DF" | "MF" | "FW";
  shirt: number;
}

export interface Team {
  team_id: string;
  name: string;
  short_name: string;
  colors: [string, string];
  style: string;
  players: Player[];
}

export interface TeamSummary {
  team_id: string;
  name: string;
  short_name: string;
  colors: [string, string];
  style: string;
  venue: string;
}

export interface MatchMeta {
  match_id: string;
  seed: number;
  home: Team;
  away: Team;
  venue: string;
  competition: string;
}

export interface MatchInfo {
  match_id: string;
  meta: MatchMeta;
  score: [number, number];
  status: "running" | "finished";
  clock: string;
  speed: number;
  events_so_far: number;
}

export interface TeamStats {
  passes: number;
  passes_completed: number;
  pass_accuracy: number;
  shots: number;
  shots_on_target: number;
  goals: number;
  xg: number;
  possession_seconds: number;
  possession_pct: number;
  pressures: number;
  tackles_won: number;
  fouls: number;
  final_third_entries: number;
}

export interface PlayerStats {
  player_id: string;
  name: string;
  team_id: string;
  passes: number;
  passes_completed: number;
  shots: number;
  goals: number;
  xg: number;
  pressures: number;
  key_passes: number;
}

export interface StatsSnapshot {
  t: number;
  clock: string;
  score: [number, number];
  home_id: string;
  away_id: string;
  team_names: Record<string, string>;
  teams: Record<string, TeamStats>;
  players: Record<string, PlayerStats>;
  momentum: number;
  pressure_index: Record<string, number>;
  last5: Record<string, TeamStats>;
}

export interface Moment {
  moment_id: string;
  type:
    | "goal"
    | "big_chance"
    | "momentum_shift"
    | "pressure_spike"
    | "milestone"
    | "card"
    | "period_end";
  t: number;
  clock: string;
  team_id: string | null;
  player_id: string | null;
  event_ids: number[];
  facts: Record<string, number | string>;
  severity: number;
}

export interface Evidence {
  stat: string;
  value: string;
}

/** One crew member's turn while producing an insight. */
export interface AgentStep {
  agent: string;
  ms: number;
  tool_calls: number;
  ok: boolean;
}

export interface Insight {
  insight_id: string;
  moment_id: string;
  profile: Profile;
  lang: Lang;
  headline: string;
  why_it_matters: string;
  evidence: Evidence[];
  confidence: number;
  verified: boolean;
  source: "llm" | "template";
  /** Empty for templates; the agent crew lists analyst, narrator, fact checker and producer. */
  trace: AgentStep[];
}

export interface Recap {
  profile: Profile;
  lang: Lang;
  title: string;
  paragraphs: string[];
  key_moments: string[];
  source: "llm" | "template";
}

export interface Cue {
  cue_id: string;
  t_start: number;
  duration_s: number;
  layer: Layer;
  text: string;
  lang: Lang;
  profile: Profile;
  moment_id: string;
  /** Match clock at which the UI received the cue; set client-side for live cues. */
  shown_from?: number;
}

/** Optional features this deployment serves (`GET /api/features`). */
export interface Features {
  ask_the_match: boolean;
  /** Azure AI Speech narration: audio endpoints are live and the switch is shown. */
  narration: boolean;
}

export interface AskRequest {
  question: string;
  profile: Profile;
  lang: Lang;
  conversation_id?: string | null;
}

/** One answer of the "Ask the match" agent; citations are checked against the live statistics. */
export interface AskResult {
  conversation_id: string;
  answer: string;
  citations: Evidence[];
  verified: boolean;
  grounded: boolean;
  source: "llm" | "template";
  trace: AgentStep[];
}

export interface UserProfile {
  user_id: string;
  profile: Profile;
  lang: Lang;
  favorite_team: string | null;
  favorite_player: string | null;
}
