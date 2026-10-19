import { formatTrace } from "../lib/trace";
import type { Insight, Lang, MatchMeta, Moment } from "../types";

interface Props {
  insights: Insight[];
  moments: Moment[];
  meta: MatchMeta;
  lang: Lang;
  favorite: string | null;
}

export function InsightFeed({ insights, moments, meta, lang, favorite }: Props) {
  const byMoment = new Map(moments.map((m) => [m.moment_id, m]));
  const rows = insights
    .map((i) => ({ i, m: byMoment.get(i.moment_id) }))
    .filter(({ m }) => m && (favorite === null || m.team_id === null || m.team_id === favorite))
    .sort((a, b) => (b.m!.t ?? 0) - (a.m!.t ?? 0));
  return (
    <section className="insights" aria-label={lang === "en" ? "Insights" : "Lecturas"}>
      <h2>{lang === "en" ? "Why it matters" : "Por qué importa"}</h2>
      {rows.length === 0 ? (
        <p className="empty">{lang === "en" ? "Insights appear as key moments happen." : "Las lecturas aparecen con cada momento clave."}</p>
      ) : null}
      <ul>
        {rows.map(({ i, m }) => {
          const team = m!.team_id ? (m!.team_id === meta.home.team_id ? meta.home : meta.away) : null;
          return (
            <li key={i.insight_id} style={{ ["--team" as string]: team?.colors[0] ?? "var(--mist)" }}>
              <header>
                <span className="insight__clock">{m!.clock}</span>
                <span className="insight__type">{m!.type.replace("_", " ")}</span>
                {i.verified ? <span className="badge badge--verified">verified</span> : null}
                <span className={`badge badge--source`}>
                  {i.source !== "llm" ? "template" : i.trace.length ? "Agent crew" : "Foundry"}
                </span>
              </header>
              <h3>{i.headline}</h3>
              <p>{i.why_it_matters}</p>
              {i.evidence.length ? (
                <ul className="chips">
                  {i.evidence.map((e) => (
                    <li key={e.stat}>
                      <span>{e.stat.replace("_", " ")}</span> {e.value}
                    </li>
                  ))}
                </ul>
              ) : null}
              {i.trace.length ? (
                <ol className="trace" aria-label={lang === "en" ? "Agent timeline" : "Línea de agentes"}>
                  {formatTrace(i.trace, lang).map((label, idx) => (
                    <li
                      key={`${i.trace[idx].agent}-${idx}`}
                      className={`trace__step trace__step--${i.trace[idx].agent}`}
                      style={{ flexGrow: Math.max(i.trace[idx].ms, 200) }}
                      title={label}
                    >
                      {label}
                    </li>
                  ))}
                </ol>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
