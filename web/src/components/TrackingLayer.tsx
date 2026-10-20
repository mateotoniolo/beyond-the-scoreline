import { useEffect, useMemo, useRef } from "react";
import type { TrackingSource } from "../hooks/useTracking";
import type { MatchMeta } from "../types";

const PITCH_H = 65; // the pitch SVG draws 100 x 100 event units as 100 x 65

/** Rolling draw statistics (Performance API), readable as `window.__btsTracking`. */
export const trackingStats = { frames: 0, drawMs: 0, maxDrawMs: 0, since: 0 };
declare global {
  interface Window {
    __btsTracking?: typeof trackingStats;
  }
}

interface Props {
  meta: MatchMeta;
  source: TrackingSource;
}

/**
 * The 22 dots and the ball inside the pitch SVG. React renders one group per squad player once;
 * a `requestAnimationFrame` loop then writes transforms straight to the DOM, so a frame never
 * costs a React render.
 */
export function TrackingLayer({ meta, source }: Props) {
  const nodes = useRef(new Map<string, SVGGElement>());
  const ball = useRef<SVGCircleElement>(null);
  const squads = useMemo(
    () =>
      [meta.home, meta.away].flatMap((team) =>
        team.players.map((p) => ({ id: p.player_id, shirt: p.shirt, colour: team.colors[0] })),
      ),
    [meta],
  );

  useEffect(() => {
    let raf = 0;
    trackingStats.since = performance.now();
    window.__btsTracking = trackingStats;
    const draw = () => {
      const started = performance.now();
      const frame = source.frameAt();
      for (const [pid, g] of nodes.current) {
        const xy = frame?.players[pid];
        if (!xy) {
          g.style.display = "none";
          continue;
        }
        g.style.display = "";
        g.setAttribute("transform", `translate(${xy[0].toFixed(2)} ${((xy[1] * PITCH_H) / 100).toFixed(2)})`);
      }
      const b = ball.current;
      if (b) {
        if (frame) {
          b.style.display = "";
          b.setAttribute("transform", `translate(${frame.ball[0].toFixed(2)} ${((frame.ball[1] * PITCH_H) / 100).toFixed(2)})`);
        } else {
          b.style.display = "none";
        }
      }
      const ms = performance.now() - started;
      trackingStats.frames += 1;
      trackingStats.drawMs += ms;
      if (ms > trackingStats.maxDrawMs) trackingStats.maxDrawMs = ms;
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [source]);

  return (
    <g className="tracking" aria-hidden="true">
      {squads.map((p) => (
        <g
          key={p.id}
          className="tracking__player"
          style={{ display: "none" }}
          ref={(el) => {
            if (el) nodes.current.set(p.id, el);
            else nodes.current.delete(p.id);
          }}
        >
          <circle r={1.4} fill={p.colour} className="tracking__dot" />
          <text y={0.6} textAnchor="middle" className="tracking__shirt">
            {p.shirt}
          </text>
        </g>
      ))}
      <circle ref={ball} r={0.8} className="tracking__ball" style={{ display: "none" }} />
    </g>
  );
}
