import type {
  AskRequest,
  AskResult,
  Cue,
  Insight,
  Lang,
  MatchInfo,
  Profile,
  Recap,
  StatsSnapshot,
  TeamSummary,
  UserProfile,
} from "./types";

async function json<T>(input: string, init?: RequestInit): Promise<T> {
  const res = await fetch(input, init);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return (await res.json()) as T;
}

const variant = (profile: Profile, lang: Lang) => `profile=${profile}&lang=${lang}`;

export const getTeams = () => json<TeamSummary[]>("/api/teams");

export const createMatch = (body: { seed: number; home: string; away: string; speed: number }) =>
  json<MatchInfo>("/api/matches", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

export const getMatch = (id: string) => json<MatchInfo>(`/api/matches/${id}`);

export const setSpeed = (id: string, speed: number) =>
  json<MatchInfo>(`/api/matches/${id}/speed`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ speed }),
  });

export const getStats = (id: string) => json<StatsSnapshot>(`/api/matches/${id}/stats`);

export const getInsights = (id: string, profile: Profile, lang: Lang) =>
  json<Insight[]>(`/api/matches/${id}/insights?${variant(profile, lang)}`);

export const getCues = (id: string, profile: Profile, lang: Lang) =>
  json<Cue[]>(`/api/matches/${id}/cues?${variant(profile, lang)}`);

export const getRecap = (id: string, profile: Profile, lang: Lang) =>
  json<Recap>(`/api/matches/${id}/recap?${variant(profile, lang)}`);

export const ask = (id: string, body: AskRequest) =>
  json<AskResult>(`/api/matches/${id}/ask`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });

export const streamUrl = (id: string, profile: Profile, lang: Lang) =>
  `/api/matches/${id}/stream?${variant(profile, lang)}`;

export const getProfile = (userId: string) => json<UserProfile>(`/api/profiles/${userId}`);

export const putProfile = (userId: string, body: Omit<UserProfile, "user_id">) =>
  json<UserProfile>(`/api/profiles/${userId}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
