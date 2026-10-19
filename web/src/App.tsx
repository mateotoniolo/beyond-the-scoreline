import { useEffect, useMemo, useState } from "react";
import { createMatch, getProfile, getRecap, getTeams, putProfile } from "./api";
import { Controls, type Setup } from "./components/Controls";
import { EventFeed } from "./components/EventFeed";
import { InsightFeed } from "./components/InsightFeed";
import { Overlays } from "./components/Overlays";
import { Pitch } from "./components/Pitch";
import { RecapDialog } from "./components/RecapDialog";
import { Scoreboard } from "./components/Scoreboard";
import { StatsPanel } from "./components/StatsPanel";
import { useMatchStream } from "./hooks/useMatchStream";
import { activeCues } from "./lib/cues";
import type { Lang, MatchInfo, Profile, Recap, TeamSummary } from "./types";

const USER_KEY = "bts.user_id";

function userId(): string {
  try {
    const existing = localStorage.getItem(USER_KEY);
    if (existing) return existing;
    const fresh = `u-${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(USER_KEY, fresh);
    return fresh;
  } catch {
    return "anonymous";
  }
}

export default function App() {
  const [teams, setTeams] = useState<TeamSummary[]>([]);
  const [uid] = useState(userId);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const [setup, setSetup] = useState<Setup>({ seed: 11, home: "t1", away: "t2", speed: 30 });
  const [profile, setProfile] = useState<Profile>("analyst");
  const [lang, setLang] = useState<Lang>("en");
  const [favorite, setFavorite] = useState<string | null>(null);
  const [info, setInfo] = useState<MatchInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recap, setRecap] = useState<Recap | null>(null);
  const [recapSeen, setRecapSeen] = useState<string | null>(null);

  useEffect(() => {
    getTeams().then(setTeams).catch((e: Error) => setError(e.message));
  }, []);

  // Profile, language and followed club persist per visitor (Azure Cosmos DB when configured).
  useEffect(() => {
    getProfile(uid)
      .then((p) => {
        setProfile(p.profile);
        setLang(p.lang);
        setFavorite(p.favorite_team);
      })
      .catch(() => undefined)
      .finally(() => setProfileLoaded(true));
  }, [uid]);

  useEffect(() => {
    if (!profileLoaded) return;
    putProfile(uid, { profile, lang, favorite_team: favorite, favorite_player: null }).catch(() => undefined);
  }, [uid, profileLoaded, profile, lang, favorite]);

  const stream = useMatchStream(info?.match_id ?? null, profile, lang);
  const cues = useMemo(
    () => activeCues(stream.cues, stream.clock, info?.speed ?? setup.speed),
    [stream.cues, stream.clock, info?.speed, setup.speed],
  );
  const verified = useMemo(
    () => new Set(stream.insights.filter((i) => i.verified).map((i) => i.moment_id)),
    [stream.insights],
  );

  useEffect(() => {
    if (!info || stream.status !== "finished" || recapSeen === info.match_id) return;
    setRecapSeen(info.match_id);
    getRecap(info.match_id, profile, lang).then(setRecap).catch((e: Error) => setError(e.message));
  }, [info, stream.status, profile, lang, recapSeen]);

  const play = async () => {
    setError(null);
    setRecap(null);
    try {
      setInfo(await createMatch(setup));
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="app">
      <header className="topbar">
        <Scoreboard info={info} stats={stream.stats} clock={stream.clock} status={stream.status} />
        <Controls
          teams={teams}
          setup={setup}
          onSetup={setSetup}
          onPlay={play}
          playing={info !== null}
          profile={profile}
          onProfile={setProfile}
          lang={lang}
          onLang={setLang}
          favorite={favorite}
          onFavorite={setFavorite}
        />
      </header>
      {error ? <p className="error" role="alert">{error}</p> : null}
      {info ? (
        <main className="main">
          <div className="main__monitor">
            <Pitch meta={info.meta} events={stream.events}>
              <Overlays cues={cues} moments={stream.moments} meta={info.meta} verified={verified} />
            </Pitch>
            <EventFeed events={stream.events} meta={info.meta} lang={lang} favorite={favorite} />
          </div>
          <aside className="main__rail">
            <StatsPanel stats={stream.stats} meta={info.meta} lang={lang} />
            <InsightFeed insights={stream.insights} moments={stream.moments} meta={info.meta} lang={lang} favorite={favorite} />
          </aside>
        </main>
      ) : (
        <main className="main main--empty">
          <section className="intro">
            <h1>Every pass has a story. We tell it, then we check it.</h1>
            <p>
              A seeded generator plays a football-realistic match. A deterministic layer turns events into statistics and momentum.
              A Microsoft Foundry model explains why each moment matters, a verifier checks every number, and the result reaches the screen as timed overlays,
              tuned for analysts or fans, in English or Spanish.
            </p>
            <p className="intro__hint">Seed 11 at 30× is a good first match. Clubs and players are fictional.</p>
          </section>
        </main>
      )}
      <footer className="footer">
        <span>Built on</span>
        <span className="chip">Microsoft Foundry</span>
        <span className="chip">Azure Container Apps</span>
        <span className="chip">Azure Cosmos DB</span>
        <span className="footer__note">Synthetic data only. No real clubs, players or matches.</span>
      </footer>
      <RecapDialog recap={recap} onClose={() => setRecap(null)} />
    </div>
  );
}
