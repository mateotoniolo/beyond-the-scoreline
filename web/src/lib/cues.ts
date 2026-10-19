import type { Cue } from "../types";

/**
 * Cues visible at `clockSeconds`: at most one per layer, the latest start wins.
 * `speed` is the playback factor: a cue stays on screen for `duration_s` real seconds,
 * which is `duration_s * speed` match seconds.
 */
export function activeCues(cues: Cue[], clockSeconds: number, speed = 1): Cue[] {
  const byLayer = new Map<Cue["layer"], Cue>();
  const factor = Math.max(1, speed);
  for (const cue of cues) {
    if (clockSeconds < cue.t_start || clockSeconds >= cue.t_start + cue.duration_s * factor) continue;
    const current = byLayer.get(cue.layer);
    if (!current || cue.t_start >= current.t_start) byLayer.set(cue.layer, cue);
  }
  const order: Cue["layer"][] = ["lower_third", "side_panel", "ticker"];
  return order.flatMap((layer) => {
    const cue = byLayer.get(layer);
    return cue ? [cue] : [];
  });
}
