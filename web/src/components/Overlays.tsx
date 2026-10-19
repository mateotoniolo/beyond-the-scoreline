import type { Cue, MatchMeta, Moment } from "../types";

interface Props {
  cues: Cue[];
  moments: Moment[];
  meta: MatchMeta;
  verified: Set<string>;
}

export function Overlays({ cues, moments, meta, verified }: Props) {
  const lower = cues.find((c) => c.layer === "lower_third");
  const side = cues.find((c) => c.layer === "side_panel");
  const ticker = cues.find((c) => c.layer === "ticker");
  const teamColour = (cue: Cue) => {
    const m = moments.find((x) => x.moment_id === cue.moment_id);
    if (!m?.team_id) return "var(--chalk)";
    return m.team_id === meta.home.team_id ? meta.home.colors[0] : meta.away.colors[0];
  };
  return (
    <>
      {side ? (
        <aside key={side.cue_id} className="overlay overlay--side" aria-live="polite">
          <p>{side.text}</p>
        </aside>
      ) : null}
      {lower ? (
        <div key={lower.cue_id} className="overlay overlay--lower" style={{ ["--team" as string]: teamColour(lower) }} aria-live="polite">
          <span className="overlay__bar" aria-hidden="true" />
          <span className="overlay__headline">{lower.text}</span>
          {verified.has(lower.moment_id) ? <span className="badge badge--verified">verified</span> : null}
        </div>
      ) : null}
      {ticker ? (
        <div key={ticker.cue_id} className="overlay overlay--ticker">
          <span>{ticker.text}</span>
        </div>
      ) : null}
    </>
  );
}
