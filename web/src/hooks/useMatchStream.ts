import { useEffect, useState } from "react";
import { getCues, getInsights, streamUrl } from "../api";
import { mergeCues } from "../lib/cues";
import type { Cue, Insight, Lang, MatchEvent, MatchInfo, Moment, Profile, StatsSnapshot } from "../types";

const MAX_EVENTS = 60;

export interface MatchStream {
  events: MatchEvent[];
  stats: StatsSnapshot | null;
  moments: Moment[];
  insights: Insight[];
  cues: Cue[];
  status: MatchInfo["status"] | "connecting";
  clock: number;
}

const empty: MatchStream = {
  events: [],
  stats: null,
  moments: [],
  insights: [],
  cues: [],
  status: "connecting",
  clock: 0,
};

function upsert<T>(list: T[], item: T, key: keyof T): T[] {
  const index = list.findIndex((x) => x[key] === item[key]);
  if (index === -1) return [...list, item];
  const next = list.slice();
  next[index] = item;
  return next;
}

/** Subscribes to a match's SSE stream for one profile and language. */
export function useMatchStream(matchId: string | null, profile: Profile, lang: Lang): MatchStream {
  const [state, setState] = useState<MatchStream>(empty);

  useEffect(() => {
    if (!matchId) return;
    setState(empty);
    const source = new EventSource(streamUrl(matchId, profile, lang));
    let open = true;

    // Insights and cues produced before this subscription (e.g. after a profile switch).
    Promise.all([getInsights(matchId, profile, lang), getCues(matchId, profile, lang)])
      .then(([insights, cues]) => {
        if (!open) return;
        setState((s) => ({
          ...s,
          insights: insights.reduce((acc, i) => upsert(acc, i, "insight_id"), s.insights),
          cues: cues.reduce((acc, c) => upsert(acc, c, "cue_id"), s.cues),
        }));
      })
      .catch(() => undefined);

    const on = <T,>(type: string, handler: (data: T) => void) =>
      source.addEventListener(type, (e) => handler(JSON.parse((e as MessageEvent).data) as T));

    on<MatchInfo>("status", (info) => {
      // The server closes the stream at full time; without this EventSource would reconnect forever.
      if (info.status === "finished") source.close();
      setState((s) => ({ ...s, status: info.status }));
    });
    on<MatchEvent>("event", (event) =>
      setState((s) => ({
        ...s,
        clock: event.t,
        events: s.events.length >= MAX_EVENTS ? [...s.events.slice(-MAX_EVENTS + 1), event] : [...s.events, event],
      })),
    );
    on<StatsSnapshot>("stats", (stats) => setState((s) => ({ ...s, stats, clock: Math.max(s.clock, stats.t) })));
    on<Moment>("moment", (moment) =>
      setState((s) => ({ ...s, moments: upsert(s.moments, moment, "moment_id") })),
    );
    on<Insight>("insight", (insight) =>
      setState((s) => ({ ...s, insights: upsert(s.insights, insight, "insight_id") })),
    );
    on<Cue[]>("cues", (cues) => setState((s) => ({ ...s, cues: mergeCues(s.cues, cues, s.clock) })));
    source.onerror = () => {
      setState((s) => {
        if (s.status === "finished") source.close();
        return s;
      });
    };

    return () => {
      open = false;
      source.close();
    };
  }, [matchId, profile, lang]);

  return state;
}
