import { useCallback, useEffect, useRef, useState } from "react";
import { insightAudioUrl } from "../api";
import { NarrationQueue, htmlAudioPlayer, readPreference, writePreference } from "../lib/narration";
import type { Insight, Lang, Profile } from "../types";

export interface Narration {
  enabled: boolean;
  setEnabled: (on: boolean) => void;
  /** Stop the current clip and drop the pending ones (the recap is about to play). */
  stop: () => void;
  /** Call inside a user gesture so the browser lets later clips start on their own. */
  unlock: () => void;
}

export interface NarrationOptions {
  /** Remember the switch in localStorage (the dashboard); false on the program output. */
  persist?: boolean;
  /** The initial state instead of the remembered one. */
  initial?: boolean;
}

const storage = (): Storage | null => {
  try {
    return typeof localStorage === "undefined" ? null : localStorage;
  } catch {
    return null;
  }
};

/**
 * Reads new verified insights aloud while the switch is on. Insights that arrive while it is
 * off are marked as handled, so switching on mid-match narrates only what comes next; a new
 * match forgets everything and a profile or language change drops the clips of the old variant.
 */
export function useNarration(
  matchId: string | null,
  insights: Insight[],
  profile: Profile,
  lang: Lang,
  available: boolean,
  options: NarrationOptions = {},
): Narration {
  const persist = options.persist !== false;
  const [enabled, setEnabledState] = useState(() => options.initial ?? readPreference(storage()));
  const player = useRef<ReturnType<typeof htmlAudioPlayer> | null>(null);
  const queue = useRef<NarrationQueue | null>(null);
  const get = () => {
    if (!queue.current) {
      player.current = htmlAudioPlayer();
      queue.current = new NarrationQueue(player.current);
    }
    return queue.current;
  };

  useEffect(() => {
    get().reset();
  }, [matchId]);

  useEffect(() => {
    get().clear();
  }, [profile, lang]);

  useEffect(() => {
    get().setEnabled(available && enabled);
  }, [available, enabled]);

  useEffect(() => {
    if (!matchId) return;
    const q = get();
    for (const i of insights) {
      if (!i.verified) continue;
      if (available && enabled) q.enqueue(i.insight_id, insightAudioUrl(matchId, i.moment_id, i.profile, i.lang));
      else q.mark(i.insight_id);
    }
  }, [matchId, insights, available, enabled]);

  const unlock = useCallback(() => {
    get();
    player.current?.unlock();
  }, []);
  const setEnabled = useCallback(
    (on: boolean) => {
      if (persist) writePreference(storage(), on);
      if (on) unlock();
      setEnabledState(on);
    },
    [unlock, persist],
  );
  const stop = useCallback(() => get().clear(), []);

  return { enabled, setEnabled, stop, unlock };
}
