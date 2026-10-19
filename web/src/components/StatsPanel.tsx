import type { Lang, MatchMeta, StatsSnapshot } from "../types";

interface Props {
  stats: StatsSnapshot | null;
  meta: MatchMeta;
  lang: Lang;
}

const LABELS: Record<Lang, Record<string, string>> = {
  en: { possession: "Possession", passes: "Passes", accuracy: "Pass accuracy", shots: "Shots (on target)", xg: "Expected goals", pressures: "Pressures", entries: "Final-third entries", momentum: "Momentum", stats: "Match stats" },
  es: { possession: "Posesión", passes: "Pases", accuracy: "Precisión de pase", shots: "Remates (al arco)", xg: "Goles esperados", pressures: "Presiones", entries: "Entradas al último tercio", momentum: "Momentum", stats: "Estadísticas" },
};

export function StatsPanel({ stats, meta, lang }: Props) {
  const L = LABELS[lang];
  const home = stats?.teams[meta.home.team_id];
  const away = stats?.teams[meta.away.team_id];
  const pct = home?.possession_pct ?? 50;
  const momentum = stats?.momentum ?? 0;
  const row = (label: string, h: string | number, a: string | number) => (
    <div className="stat" key={label}>
      <span className="stat__home">{h}</span>
      <span className="stat__label">{label}</span>
      <span className="stat__away">{a}</span>
    </div>
  );
  return (
    <section className="stats" aria-label={L.stats}>
      <h2>{L.stats}</h2>
      <div className="possession" aria-label={`${L.possession} ${pct.toFixed(0)}%`}>
        <span style={{ width: `${pct}%`, background: meta.home.colors[0] }} />
        <span style={{ width: `${100 - pct}%`, background: meta.away.colors[0] }} />
      </div>
      {row(L.possession, `${pct.toFixed(0)}%`, `${(100 - pct).toFixed(0)}%`)}
      {row(L.passes, home ? `${home.passes_completed}/${home.passes}` : "–", away ? `${away.passes_completed}/${away.passes}` : "–")}
      {row(L.accuracy, home ? `${(home.pass_accuracy * 100).toFixed(0)}%` : "–", away ? `${(away.pass_accuracy * 100).toFixed(0)}%` : "–")}
      {row(L.shots, home ? `${home.shots} (${home.shots_on_target})` : "–", away ? `${away.shots} (${away.shots_on_target})` : "–")}
      {row(L.xg, home ? home.xg.toFixed(2) : "–", away ? away.xg.toFixed(2) : "–")}
      {row(L.pressures, home?.pressures ?? "–", away?.pressures ?? "–")}
      {row(L.entries, home?.final_third_entries ?? "–", away?.final_third_entries ?? "–")}
      <div className="momentum" aria-label={`${L.momentum} ${momentum.toFixed(2)}`}>
        <span className="momentum__label">{L.momentum}</span>
        <div className="momentum__track">
          <i className="momentum__marker" style={{ left: `${50 + momentum * 50}%`, background: momentum >= 0 ? meta.home.colors[0] : meta.away.colors[0] }} />
        </div>
      </div>
    </section>
  );
}
