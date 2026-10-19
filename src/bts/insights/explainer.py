"""Ask the model to explain a moment; returns an unverified insight."""

from __future__ import annotations

from pydantic import BaseModel

from bts.insights import templates
from bts.insights.llm import LLMClient
from bts.insights.prompts import explainer_system, explainer_user
from bts.insights.schemas import Insight, Lang, Profile, Recap
from bts.insights.verifier import ExplainerOutput
from bts.sim.models import Event
from bts.stats.moments import Moment
from bts.stats.state import StatsSnapshot


class RecapOutput(BaseModel):
    title: str
    paragraphs: list[str]
    key_moments: list[str]


def to_insight(out: ExplainerOutput, moment: Moment, profile: Profile, lang: Lang) -> Insight:
    """An unverified insight from a model reply (shared by the simple pipeline and the crew)."""
    return Insight(
        insight_id=f"{moment.moment_id}:{profile}:{lang}",
        moment_id=moment.moment_id,
        profile=profile,
        lang=lang,
        headline=out.headline.strip(),
        why_it_matters=out.why_it_matters.strip(),
        evidence=out.evidence,
        confidence=max(0.0, min(1.0, out.confidence)),
        verified=False,
        source="llm",
    )


def recap_from_output(
    out: RecapOutput, snap: StatsSnapshot, moments: list[Moment], profile: Profile, lang: Lang
) -> Recap:
    """A recap from a model reply, or the template when the reply is empty."""
    paragraphs = [p.strip() for p in out.paragraphs if p.strip()]
    if not out.title.strip() or not paragraphs:
        return templates.render_recap(snap, moments, profile, lang)
    return Recap(
        profile=profile,
        lang=lang,
        title=out.title.strip(),
        paragraphs=paragraphs,
        key_moments=out.key_moments,
        source="llm",
    )


async def explain(
    llm: LLMClient,
    moment: Moment,
    snap: StatsSnapshot,
    recent: list[Event],
    profile: Profile,
    lang: Lang,
    issues: list[str] | None = None,
) -> Insight:
    out: ExplainerOutput = await llm.complete_json(
        system=explainer_system(profile, lang),
        user=explainer_user(moment, snap, recent, issues),
        schema=ExplainerOutput,
    )
    return to_insight(out, moment, profile, lang)
