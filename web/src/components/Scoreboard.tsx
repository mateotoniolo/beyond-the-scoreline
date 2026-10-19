import type { MatchInfo, StatsSnapshot } from "../types";
import { clockOf } from "../lib/format";

interface Props {
  info: MatchInfo | null;
  stats: StatsSnapshot | null;
  clock: number;
  status: string;
}

export function Scoreboard({ info, stats, clock, status }: Props) {
  if (!info) {
    return (
      <div className="scoreboard scoreboard--idle">
        <span className="scoreboard__title">Beyond the Scoreline</span>
        <span className="scoreboard__sub">Pick a seed and press play</span>
      </div>
    );
  }
  const { home, away } = info.meta;
  const score = stats?.score ?? info.score;
  const live = status === "running";
  return (
    <div className="scoreboard">
      <span className="scoreboard__team" style={{ ["--team" as string]: home.colors[0] }}>
        <i className="crest" aria-hidden="true" />
        {home.name}
      </span>
      <span className="scoreboard__score" aria-label={`${home.name} ${score[0]}, ${away.name} ${score[1]}`}>
        {score[0]}
        <span className="scoreboard__dash">–</span>
        {score[1]}
      </span>
      <span className="scoreboard__team scoreboard__team--away" style={{ ["--team" as string]: away.colors[0] }}>
        {away.name}
        <i className="crest" aria-hidden="true" />
      </span>
      <span className={`scoreboard__clock${live ? " is-live" : ""}`}>
        <i className="live-dot" aria-hidden="true" />
        {clockOf(clock)}
        <small>{live ? "live" : status === "finished" ? "full time" : "…"}</small>
      </span>
    </div>
  );
}
