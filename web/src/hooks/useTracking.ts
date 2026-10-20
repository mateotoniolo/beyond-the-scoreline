import { useEffect, useMemo, useRef } from "react";
import { getTracking } from "../api";
import { FPS, KEEP_BEHIND_S, MAX_FRAMES, TrackingBuffer } from "../lib/tracking";
import type { Frame } from "../types";

/** What a drawing loop reads every animation frame: the frame at the extrapolated clock. */
export interface TrackingSource {
  frameAt(): Frame | null;
}

const NONE: TrackingSource = { frameAt: () => null };

/**
 * Keeps synthetic tracking frames buffered ahead of the stream clock. Whenever the clock moves
 * it drops old frames and, when fewer than `AHEAD_S` seconds lie ahead, fetches the next window
 * (one request in flight at a time). `frameAt` extrapolates the stream clock by the playback
 * speed so the dots keep moving between events, never past the buffer's end.
 */
export function useTracking(matchId: string | null, enabled: boolean, clock: number, speed: number): TrackingSource {
  const buffer = useRef<TrackingBuffer | null>(null);
  const inflight = useRef(false);
  const tick = useRef({ t: 0, at: 0 });
  const speedRef = useRef(speed);
  speedRef.current = speed;

  useEffect(() => {
    buffer.current = matchId && enabled ? new TrackingBuffer() : null;
    inflight.current = false;
  }, [matchId, enabled]);

  useEffect(() => {
    tick.current = { t: clock, at: performance.now() };
    const b = buffer.current;
    if (!matchId || !b) return;
    b.prune(clock - KEEP_BEHIND_S);
    const window = b.nextWindow(clock);
    if (!window || inflight.current) return;
    inflight.current = true;
    const [from, to] = window;
    getTracking(matchId, from, to)
      .then((frames) => {
        if (buffer.current !== b) return; // a new match or the switch went off meanwhile
        b.add(frames);
        const expected = Math.min(MAX_FRAMES, Math.floor((to - from) * FPS + 1e-9) + 1);
        if (frames.length < expected) b.markEnd();
      })
      .catch(() => undefined)
      .finally(() => {
        if (buffer.current === b) inflight.current = false;
      });
  }, [matchId, enabled, clock]);

  return useMemo(
    () =>
      enabled
        ? {
            frameAt() {
              const b = buffer.current;
              const cover = b?.coverage();
              if (!b || !cover) return null;
              const { t, at } = tick.current;
              const now = t + ((performance.now() - at) / 1000) * speedRef.current;
              return b.at(Math.min(now, cover.to));
            },
          }
        : NONE,
    [enabled],
  );
}
