import type { Lang } from "../types";

/** A clip whose turn comes later than this after it was queued is stale: the match moved on. */
export const STALE_MS = 60_000;
export const STORAGE_KEY = "bts.narration";

export const LABELS: Record<Lang, { toggle: string; listen: string; stop: string; unavailable: string }> = {
  en: { toggle: "Narration", listen: "Listen", stop: "Stop", unavailable: "Audio unavailable" },
  es: { toggle: "Narración", listen: "Escuchar", stop: "Detener", unavailable: "Audio no disponible" },
};

/** Plays one clip; the promise settles when playback ends, fails or is stopped. */
export interface Player {
  play(url: string): Promise<void>;
  stop(): void;
}

interface Item {
  key: string;
  url: string;
  at: number;
}

/**
 * One clip at a time, in arrival order, each key at most once. Off by default: while off,
 * enqueues are ignored and switching off stops the current clip and drops the rest.
 */
export class NarrationQueue {
  private on = false;
  private items: Item[] = [];
  private current: string | null = null;
  private seen = new Set<string>();
  private readonly player: Player;
  private readonly now: () => number;

  constructor(player: Player, now: () => number = Date.now) {
    this.player = player;
    this.now = now;
  }

  get enabled(): boolean {
    return this.on;
  }
  get pending(): number {
    return this.items.length;
  }
  get playing(): string | null {
    return this.current;
  }

  setEnabled(on: boolean): void {
    this.on = on;
    if (!on) this.clear();
  }

  /** True when the clip was queued; false when narration is off or the key was already handled. */
  enqueue(key: string, url: string): boolean {
    if (!this.on || this.seen.has(key)) return false;
    this.seen.add(key);
    this.items.push({ key, url, at: this.now() });
    if (this.current === null) this.next();
    return true;
  }

  /** Remember a key as handled without playing it (the backlog when narration is switched on). */
  mark(key: string): void {
    this.seen.add(key);
  }

  /** Stop the current clip and drop the pending ones; handled keys stay handled. */
  clear(): void {
    this.items = [];
    if (this.current !== null) {
      this.current = null;
      this.player.stop();
    }
  }

  /** A new match: nothing pending, nothing remembered. */
  reset(): void {
    this.clear();
    this.seen.clear();
  }

  private next(): void {
    while (this.items.length) {
      const item = this.items.shift()!;
      if (this.now() - item.at > STALE_MS) continue;
      this.current = item.key;
      this.player
        .play(item.url)
        .catch(() => undefined)
        .then(() => {
          if (this.current !== item.key) return; // stopped or cleared meanwhile
          this.current = null;
          this.next();
        });
      return;
    }
  }
}

export function readPreference(storage: Pick<Storage, "getItem"> | null): boolean {
  try {
    return storage?.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function writePreference(storage: Pick<Storage, "setItem"> | null, on: boolean): void {
  try {
    storage?.setItem(STORAGE_KEY, on ? "1" : "0");
  } catch {
    // private mode or storage disabled: the switch still works for this page
  }
}

// 44-byte WAV header with no samples: enough for a browser to "play" inside a user gesture.
const SILENCE =
  "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";

/**
 * One reused `HTMLAudioElement`. `unlock()` must run inside a user gesture (the switch or the
 * Play button): browsers then let the same element start later clips without another gesture.
 */
export function htmlAudioPlayer(): Player & { unlock(): void } {
  let audio: HTMLAudioElement | null = null;
  let generation = 0;
  let settle: (() => void) | null = null;
  const element = () => {
    if (!audio) {
      audio = new Audio();
      audio.preload = "auto";
    }
    return audio;
  };
  return {
    unlock() {
      const a = element();
      if (!a.paused) return;
      a.src = SILENCE;
      a.play().catch(() => undefined);
    },
    play(url: string) {
      const a = element();
      const token = ++generation;
      return new Promise<void>((resolve) => {
        // A late `ended` or `error` of an earlier clip must not settle this one.
        const finish = () => {
          if (token !== generation) return;
          a.removeEventListener("ended", finish);
          a.removeEventListener("error", finish);
          settle = null;
          resolve();
        };
        settle = finish;
        a.addEventListener("ended", finish);
        a.addEventListener("error", finish);
        a.src = url;
        a.play().catch(finish);
      });
    },
    stop() {
      if (!audio) return;
      audio.pause();
      audio.removeAttribute("src");
      settle?.();
    },
  };
}
