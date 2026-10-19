"""The producer: deterministic cue planning for the match's overlay (no model involved)."""

from __future__ import annotations

from bts.insights.cues import from_insight
from bts.insights.schemas import Cue, Insight
from bts.stats.moments import Moment

# Goals and red cards take the lower third at once instead of waiting their turn.
PREEMPT_SEVERITY = 0.9


def _end(cue: Cue, factor: float) -> float:
    """Match-time end of a cue: ``duration_s`` is in real seconds, hence the speed factor."""
    return cue.t_start + cue.duration_s * factor


def plan_cues(
    insight: Insight, moment: Moment, existing: list[Cue], speed: float = 1.0
) -> list[Cue]:
    """Cues for ``insight`` that never overlap ``existing`` cues on the same layer.

    A later cue waits until the running one ends. A severe moment takes the lower third
    immediately: the running cue comes back with its duration cut, under the same
    ``cue_id``, so clients replace it.
    """
    factor = max(1.0, speed)
    planned: list[Cue] = []
    cut: list[Cue] = []
    for cue in from_insight(insight, moment):
        same_layer = sorted((c for c in existing if c.layer == cue.layer), key=lambda c: c.t_start)
        if moment.severity >= PREEMPT_SEVERITY and cue.layer == "lower_third":
            for prev in same_layer:
                if prev.t_start < cue.t_start < _end(prev, factor):
                    shorter = round((cue.t_start - prev.t_start) / factor, 3)
                    cut.append(prev.model_copy(update={"duration_s": shorter}))
            planned.append(cue)
            continue
        start = cue.t_start
        span = cue.duration_s * factor
        for prev in same_layer:  # sorted by start, so one pass settles the whole chain
            if start < _end(prev, factor) and prev.t_start < start + span:
                start = _end(prev, factor)
        planned.append(cue if start == cue.t_start else cue.model_copy(update={"t_start": start}))
    return planned + cut
