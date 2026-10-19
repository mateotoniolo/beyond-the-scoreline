"""Ask the model to explain a moment; returns an unverified insight."""

from __future__ import annotations

from pydantic import BaseModel, Field

from bts.insights.llm import LLMClient
from bts.insights.prompts import explainer_system, explainer_user
from bts.insights.schemas import Insight, Lang, Profile
from bts.insights.verifier import ExplainerOutput
from bts.sim.models import Event
from bts.stats.moments import Moment
from bts.stats.state import StatsSnapshot


class RecapOutput(BaseModel):
    title: str
    paragraphs: list[str] = Field(min_length=1)
    key_moments: list[str] = Field(default_factory=list)


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
    return Insight(
        insight_id=f"{moment.moment_id}:{profile}:{lang}",
        moment_id=moment.moment_id,
        profile=profile,
        lang=lang,
        headline=out.headline.strip(),
        why_it_matters=out.why_it_matters.strip(),
        evidence=out.evidence,
        confidence=out.confidence,
        verified=False,
        source="llm",
    )
