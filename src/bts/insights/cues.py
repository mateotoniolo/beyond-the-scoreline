"""Turn an insight into timed, machine-readable overlay cues."""

from bts.insights.schemas import Cue, Insight
from bts.stats.moments import Moment

LOWER_THIRD_S = 8.0
SIDE_PANEL_S = 20.0
TICKER_S = 12.0


def from_insight(insight: Insight, moment: Moment) -> list[Cue]:
    base = dict(
        t_start=moment.t,
        lang=insight.lang,
        profile=insight.profile,
        moment_id=insight.moment_id,
    )
    cues = [
        Cue(
            cue_id=f"{insight.insight_id}:lower_third",
            duration_s=LOWER_THIRD_S,
            layer="lower_third",
            text=insight.headline,
            **base,
        ),
        Cue(
            cue_id=f"{insight.insight_id}:side_panel",
            duration_s=SIDE_PANEL_S,
            layer="side_panel",
            text=insight.why_it_matters,
            **base,
        ),
    ]
    if insight.profile == "analyst" and insight.evidence:
        text = "; ".join(f"{e.stat.replace('_', ' ')} {e.value}" for e in insight.evidence)
        cues.append(
            Cue(
                cue_id=f"{insight.insight_id}:ticker",
                duration_s=TICKER_S,
                layer="ticker",
                text=text,
                **base,
            )
        )
    return cues
