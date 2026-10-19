import type { Lang, MatchEvent, MatchMeta } from "../types";
import { describe, playerName, teamOf } from "../lib/format";

interface Props {
  events: MatchEvent[];
  meta: MatchMeta;
  lang: Lang;
  favorite: string | null;
}

export function EventFeed({ events, meta, lang, favorite }: Props) {
  const rows = events.slice(-24).reverse();
  return (
    <section className="feed" aria-label="Latest events">
      <h2>{lang === "en" ? "Event stream" : "Flujo de eventos"}</h2>
      <ol>
        {rows.map((e) => {
          const team = teamOf(meta, e.team_id);
          const dim = favorite !== null && favorite !== e.team_id;
          return (
            <li key={e.event_id} className={dim ? "is-dim" : undefined}>
              <span className="feed__clock">{e.clock}</span>
              <i className="dot" style={{ background: team.colors[0] }} aria-hidden="true" />
              <span className="feed__team">{team.short_name}</span>
              <span className="feed__player">{playerName(meta, e.player_id)}</span>
              <span className={`feed__what${e.outcome === "goal" ? " is-goal" : ""}`}>{describe(e, lang)}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
