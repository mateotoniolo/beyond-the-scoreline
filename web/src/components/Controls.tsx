import { LABELS } from "../lib/narration";
import type { Lang, Profile, TeamSummary } from "../types";

export interface Setup {
  seed: number;
  home: string;
  away: string;
  speed: number;
}

interface Props {
  teams: TeamSummary[];
  setup: Setup;
  onSetup: (s: Setup) => void;
  onPlay: () => void;
  playing: boolean;
  /** The program output for the running match (`#/broadcast?…`), opened in a new tab. */
  broadcastUrl: string | null;
  profile: Profile;
  onProfile: (p: Profile) => void;
  lang: Lang;
  onLang: (l: Lang) => void;
  favorite: string | null;
  onFavorite: (t: string | null) => void;
  /** Azure AI Speech narration: the switch exists only when the deployment serves audio. */
  narrationAvailable: boolean;
  narration: boolean;
  onNarration: (on: boolean) => void;
  /** Synthetic tracking dots on the pitch: the switch exists only when the API serves frames. */
  trackingAvailable: boolean;
  tracking: boolean;
  onTracking: (on: boolean) => void;
}

const SPEEDS = [1, 2, 5, 10, 30, 60, 600];

export function Controls(p: Props) {
  const { setup } = p;
  return (
    <form
      className="controls"
      onSubmit={(e) => {
        e.preventDefault();
        p.onPlay();
      }}
    >
      <label className="field">
        <span>Seed</span>
        <input
          type="number"
          min={0}
          value={setup.seed}
          onChange={(e) => p.onSetup({ ...setup, seed: Number(e.target.value) })}
        />
      </label>
      <label className="field">
        <span>Home</span>
        <select value={setup.home} onChange={(e) => p.onSetup({ ...setup, home: e.target.value })}>
          {p.teams.map((t) => (
            <option key={t.team_id} value={t.team_id} disabled={t.team_id === setup.away}>
              {t.name}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Away</span>
        <select value={setup.away} onChange={(e) => p.onSetup({ ...setup, away: e.target.value })}>
          {p.teams.map((t) => (
            <option key={t.team_id} value={t.team_id} disabled={t.team_id === setup.home}>
              {t.name}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Speed</span>
        <select value={setup.speed} onChange={(e) => p.onSetup({ ...setup, speed: Number(e.target.value) })}>
          {SPEEDS.map((s) => (
            <option key={s} value={s}>
              {s}×
            </option>
          ))}
        </select>
      </label>
      <button type="submit" className="button button--primary">
        {p.playing ? "New match" : "Play"}
      </button>
      {p.broadcastUrl ? (
        <a className="button" href={p.broadcastUrl} target="_blank" rel="noopener">
          Broadcast
        </a>
      ) : null}

      <div className="segmented" role="group" aria-label="Audience">
        <button type="button" aria-pressed={p.profile === "analyst"} onClick={() => p.onProfile("analyst")}>
          Analyst
        </button>
        <button type="button" aria-pressed={p.profile === "fan"} onClick={() => p.onProfile("fan")}>
          Fan
        </button>
      </div>
      <div className="segmented" role="group" aria-label="Language">
        <button type="button" aria-pressed={p.lang === "en"} onClick={() => p.onLang("en")}>
          English
        </button>
        <button type="button" aria-pressed={p.lang === "es"} onClick={() => p.onLang("es")}>
          Español
        </button>
      </div>
      <label className="field">
        <span>Follow</span>
        <select value={p.favorite ?? ""} onChange={(e) => p.onFavorite(e.target.value || null)}>
          <option value="">Both teams</option>
          {[setup.home, setup.away].map((id) => {
            const t = p.teams.find((x) => x.team_id === id);
            return t ? (
              <option key={id} value={id}>
                {t.name}
              </option>
            ) : null;
          })}
        </select>
      </label>
      {p.narrationAvailable ? (
        <button
          type="button"
          className="toggle"
          role="switch"
          aria-checked={p.narration}
          onClick={() => p.onNarration(!p.narration)}
        >
          <span className="toggle__dot" aria-hidden="true" />
          {LABELS[p.lang].toggle}
        </button>
      ) : null}
      {p.trackingAvailable ? (
        <button
          type="button"
          className="toggle"
          role="switch"
          aria-checked={p.tracking}
          onClick={() => p.onTracking(!p.tracking)}
        >
          <span className="toggle__dot" aria-hidden="true" />
          Tracking
        </button>
      ) : null}
    </form>
  );
}
