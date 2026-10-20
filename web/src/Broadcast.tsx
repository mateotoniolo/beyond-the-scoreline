import { useEffect, useMemo, useState } from "react";
import { getFeatures, getMatch } from "./api";
import { Overlays } from "./components/Overlays";
import { Pitch } from "./components/Pitch";
import { Scoreboard } from "./components/Scoreboard";
import { TrackingLayer } from "./components/TrackingLayer";
import { useMatchStream } from "./hooks/useMatchStream";
import { useNarration } from "./hooks/useNarration";
import { useTracking } from "./hooks/useTracking";
import { parseBroadcastHash, stageScale } from "./lib/broadcast";
import { activeCues } from "./lib/cues";
import type { Features, MatchInfo } from "./types";

const NO_FEATURES: Features = { ask_the_match: false, narration: false, tracking: false };
const LABELS = {
  en: { waiting: "Waiting for the match", fullTime: "full time", start: "Start narration", noMatch: "no match id" },
  es: { waiting: "Esperando el partido", fullTime: "final", start: "Iniciar narración", noMatch: "sin id de partido" },
};

function useStageScale(): number {
  const [scale, setScale] = useState(() => stageScale(window.innerWidth, window.innerHeight));
  useEffect(() => {
    const onResize = () => setScale(stageScale(window.innerWidth, window.innerHeight));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return scale;
}

/**
 * The program output: a 1280×720 stage (scoreboard, pitch, the producer's overlays, tracking)
 * scaled to the viewport, for a studio monitor or an OBS browser source. No controls, no feeds.
 */
export default function Broadcast() {
  const params = useMemo(() => parseBroadcastHash(window.location.hash), []);
  const labels = LABELS[params.lang];
  const [info, setInfo] = useState<MatchInfo | null>(null);
  const [missing, setMissing] = useState(false);
  const [features, setFeatures] = useState<Features>(NO_FEATURES);
  const [narrating, setNarrating] = useState(false);
  const scale = useStageScale();

  useEffect(() => {
    document.title = "Beyond the Scoreline · Broadcast";
    getFeatures().then(setFeatures).catch(() => undefined);
    if (!params.match) {
      setMissing(true);
      return;
    }
    // Match ids carry a random suffix: an unknown id stays unknown, so there is nothing to poll.
    getMatch(params.match)
      .then(setInfo)
      .catch(() => setMissing(true));
  }, [params.match]);

  const stream = useMatchStream(info?.match_id ?? null, params.profile, params.lang);
  const speed = info?.speed ?? 1;
  const cues = useMemo(() => activeCues(stream.cues, stream.clock, speed), [stream.cues, stream.clock, speed]);
  const verified = useMemo(
    () => new Set(stream.insights.filter((i) => i.verified).map((i) => i.moment_id)),
    [stream.insights],
  );
  const lower = cues.find((c) => c.layer === "lower_third");
  const lit = lower !== undefined && verified.has(lower.moment_id);
  const trackingOn = features.tracking && params.tracking;
  const trackingSource = useTracking(info?.match_id ?? null, trackingOn, stream.clock, speed);
  const narrationOn = features.narration && params.narration;
  const narration = useNarration(info?.match_id ?? null, stream.insights, params.profile, params.lang, narrationOn, {
    persist: false,
    initial: false,
  });

  const finished = info?.status === "finished" || stream.status === "finished";
  const waiting = missing || info === null || finished;
  const score = stream.stats?.score ?? info?.score;

  return (
    <div className="broadcast">
      <div className="broadcast__stage" style={{ transform: `scale(${scale})` }}>
        {waiting ? (
          <section className="broadcast__waiting">
            <h1>{labels.waiting}</h1>
            <p>
              {info && score
                ? `${info.meta.home.name} ${score[0]} – ${score[1]} ${info.meta.away.name} · ${labels.fullTime}`
                : (params.match ?? labels.noMatch)}
            </p>
          </section>
        ) : (
          <>
            <header className="broadcast__top">
              <Scoreboard info={info} stats={stream.stats} clock={stream.clock} status={stream.status} />
              <span className={`broadcast__marker${lit ? " is-on" : ""}`}>
                <i className="live-dot" aria-hidden="true" />
                {lit ? "Agent crew verified" : "Agent crew"}
              </span>
            </header>
            <Pitch
              meta={info.meta}
              events={stream.events}
              layer={trackingOn ? <TrackingLayer meta={info.meta} source={trackingSource} /> : null}
            >
              <Overlays cues={cues} moments={stream.moments} meta={info.meta} verified={verified} />
            </Pitch>
            {narrationOn && !narrating ? (
              <button
                type="button"
                className="button button--primary broadcast__start"
                onClick={() => {
                  narration.setEnabled(true); // inside the click, so the clips may start later
                  setNarrating(true);
                }}
              >
                {labels.start}
              </button>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
