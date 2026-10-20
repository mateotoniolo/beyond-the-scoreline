import { useMemo } from "react";
import { frameTeams } from "../lib/possession";
import type { MatchEvent, MatchMeta } from "../types";

interface Props {
  meta: MatchMeta;
  events: MatchEvent[];
  /** Drawn inside the SVG, over the event markers (the tracking layer). */
  layer?: React.ReactNode;
  /** Drawn over the monitor (the overlays). */
  children?: React.ReactNode;
}

const LAST = 18;
const PITCH_H = 65; // 105 m x 68 m drawn as 100 x 65 units

export function Pitch({ meta, events, layer, children }: Props) {
  const recent = events.slice(-LAST).filter((e) => e.type !== "period_start" && e.type !== "period_end");
  // Each event's frame follows possession (a save sits at the goal the shot went to).
  const frames = useMemo(() => frameTeams(events, meta.home.team_id, meta.away.team_id), [events, meta]);
  const colour = (teamId: string) => (teamId === meta.home.team_id ? meta.home.colors[0] : meta.away.colors[0]);
  // Home always attacks to the right on screen; away frames are mirrored.
  const place = (e: MatchEvent, p: { x: number; y: number }) => {
    const mirrored = (frames.get(e.event_id) ?? e.team_id) !== meta.home.team_id;
    const x = mirrored ? 100 - p.x : p.x;
    const y = (mirrored ? 100 - p.y : p.y) * (PITCH_H / 100);
    return { x, y };
  };

  return (
    <div className="monitor">
      <svg className="pitch" viewBox="0 0 100 65" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Pitch with the latest events">
        <rect x="0" y="0" width="100" height="65" className="pitch__turf" />
        <g className="pitch__lines">
          <rect x="1" y="1" width="98" height="63" />
          <line x1="50" y1="1" x2="50" y2="64" />
          <circle cx="50" cy="32.5" r="8.7" />
          <rect x="1" y="13" width="15.7" height="39" />
          <rect x="83.3" y="13" width="15.7" height="39" />
          <rect x="1" y="22.5" width="5.2" height="20" />
          <rect x="93.8" y="22.5" width="5.2" height="20" />
        </g>
        {recent.map((e, i) => {
          const s = place(e, e.start);
          const t = e.end ? place(e, e.end) : null;
          const fade = 0.25 + (0.75 * (i + 1)) / recent.length;
          const goal = e.type === "shot" && e.outcome === "goal";
          return (
            <g key={e.event_id} style={{ opacity: fade }} stroke={colour(e.team_id)} fill={colour(e.team_id)}>
              {t ? <line x1={s.x} y1={s.y} x2={t.x} y2={t.y} strokeWidth={e.type === "shot" ? 0.9 : 0.45} strokeLinecap="round" /> : null}
              <circle cx={s.x} cy={s.y} r={goal ? 2.2 : e.type === "pressure" ? 0.9 : 1.2} className={goal ? "pitch__goal" : undefined} />
            </g>
          );
        })}
        {layer}
      </svg>
      {children}
    </div>
  );
}
