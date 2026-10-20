import { useEffect, useMemo, useState } from "react";
import { createMatch, getFeatures, getProfile, getRecap, getTeams, putProfile, recapAudioUrl } from "./api";
import { AskPanel } from "./components/AskPanel";
import { Controls, type Setup } from "./components/Controls";
import { EventFeed } from "./components/EventFeed";
import { InsightFeed } from "./components/InsightFeed";
import { Overlays } from "./components/Overlays";
import { Pitch } from "./components/Pitch";
import { RecapDialog } from "./components/RecapDialog";
import { Scoreboard } from "./components/Scoreboard";
import { StatsPanel } from "./components/StatsPanel";
import { TrackingLayer } from "./components/TrackingLayer";
import { useMatchStream } from "./hooks/useMatchStream";
import { useNarration } from "./hooks/useNarration";
import { useTracking } from "./hooks/useTracking";
import { activeCues } from "./lib/cues";
import { localStorageOrNull } from "./lib/storage";
import { readPreference as readTracking, writePreference as writeTracking } from "./lib/tracking";
import type { Features, Lang, MatchInfo, Profile, Recap, TeamSummary } from "./types";

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
  const [features, setFeatures] = useState<Features>({ ask_the_match: false, narration: false, tracking: false });
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
  const [tracking, setTracking] = useState(() => readTracking(localStorageOrNull(), false));

  useEffect(() => {
    getTeams().then(setTeams).catch((e: Error) => setError(e.message));
    getFeatures().then(setFeatures).catch(() => undefined); // an old API without it: the desk stays hidden
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
  const narration = useNarration(info?.match_id ?? null, stream.insights, profile, lang, features.narration);
  const trackingOn = features.tracking && tracking;
  const trackingSource = useTracking(info?.match_id ?? null, trackingOn, stream.clock, info?.speed ?? setup.speed);
  const onTracking = (on: boolean) => {
    writeTracking(localStorageOrNull(), on);
    setTracking(on);
  };

  useEffect(() => {
    if (!info || stream.status !== "finished" || recapSeen === info.match_id) return;
    setRecapSeen(info.match_id);
    getRecap(info.match_id, profile, lang).then(setRecap).catch((e: Error) => setError(e.message));
  }, [info, stream.status, profile, lang, recapSeen]);

  const play = async () => {
    setError(null);
    setRecap(null);
    if (narration.enabled) narration.unlock(); // inside the click, so the clips may start later
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
          narrationAvailable={features.narration}
          narration={narration.enabled}
          onNarration={narration.setEnabled}
          trackingAvailable={features.tracking}
          tracking={tracking}
          onTracking={onTracking}
        />
      </header>
      {error ? <p className="error" role="alert">{error}</p> : null}
      {info ? (
        <main className="main">
          <div className="main__monitor">
            <Pitch
              meta={info.meta}
              events={stream.events}
              layer={trackingOn ? <TrackingLayer meta={info.meta} source={trackingSource} /> : null}
            >
              <Overlays cues={cues} moments={stream.moments} meta={info.meta} verified={verified} />
            </Pitch>
            <EventFeed events={stream.events} meta={info.meta} lang={lang} favorite={favorite} />
          </div>
          <aside className="main__rail">
            <StatsPanel stats={stream.stats} meta={info.meta} lang={lang} />
            <InsightFeed insights={stream.insights} moments={stream.moments} meta={info.meta} lang={lang} favorite={favorite} />
            {features.ask_the_match ? (
              <AskPanel key={info.match_id} matchId={info.match_id} profile={profile} lang={lang} />
            ) : null}
          </aside>
        </main>
      ) : (
        <main className="main main--empty">
          <section className="intro">
            <h1>Every pass has a story. We tell it, then we check it.</h1>
            <p>
              A seeded generator plays a football-realistic match. A deterministic layer turns events into statistics and momentum.
              A crew of Microsoft Agent Framework agents on a Foundry model, a tactical analyst, a narrator and a fact checker, explains why each moment matters;
              a producer re-checks every number, and the result reaches the screen as timed overlays, tuned for analysts or fans, in English or Spanish.
            </p>
            <p className="intro__hint">Seed 11 at 30× is a good first match. Clubs and players are fictional.</p>
          </section>
        </main>
      )}
      <footer className="footer">
        <span>Built on</span>
        <span className="chip">Microsoft Foundry</span>
        <span className="chip">Microsoft Agent Framework</span>
        <span className="chip">Azure Container Apps</span>
        <span className="chip">Azure Cosmos DB</span>
        {features.narration ? <span className="chip">Azure AI Speech</span> : null}
        <span className="footer__note">Synthetic data only. No real clubs, players or matches.</span>
      </footer>
      <RecapDialog
        recap={recap}
        onClose={() => setRecap(null)}
        lang={lang}
        audioUrl={features.narration && info ? recapAudioUrl(info.match_id, profile, lang) : null}
        onListen={narration.stop}
      />
    </div>
  );
}
