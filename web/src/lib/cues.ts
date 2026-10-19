import type { Cue } from "../types";

/**
 * Cues visible at `clockSeconds`: at most one per layer, the latest start wins.
 * `speed` is the playback factor: a cue stays on screen for `duration_s` real seconds,
 * which is `duration_s * speed` match seconds.
 */
export function activeCues(cues: Cue[], clockSeconds: number, speed = 1): Cue[] {
  const byLayer = new Map<Cue["layer"], Cue>();
  const factor = Math.max(1, speed);
  const startOf = (cue: Cue) => Math.max(cue.t_start, cue.shown_from ?? cue.t_start);
  for (const cue of cues) {
    const start = startOf(cue);
    if (clockSeconds < start || clockSeconds >= start + cue.duration_s * factor) continue;
    const current = byLayer.get(cue.layer);
    if (!current || start >= startOf(current)) byLayer.set(cue.layer, cue);
  }
  const order: Cue["layer"][] = ["lower_third", "side_panel", "ticker"];
  return order.flatMap((layer) => {
    const cue = byLayer.get(layer);
    return cue ? [cue] : [];
  });
}

/**
 * Upserts incoming cues by `cue_id`. A new cue is anchored at `clock` (shown from the moment it
 * arrives, so model latency never hides it); a replaced cue, such as one the producer cut short,
 * keeps the anchor it already had.
 */
export function mergeCues(existing: Cue[], incoming: Cue[], clock: number): Cue[] {
  const next = existing.slice();
  for (const cue of incoming) {
    const index = next.findIndex((c) => c.cue_id === cue.cue_id);
    if (index === -1) next.push({ ...cue, shown_from: clock });
    else next[index] = { ...cue, shown_from: next[index].shown_from ?? clock };
  }
  return next;
}
