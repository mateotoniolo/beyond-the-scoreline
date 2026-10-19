"""Explain → verify → retry once → template. Never blocks the event stream."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from bts.insights import templates
from bts.insights.explainer import RecapOutput, explain, recap_from_output
from bts.insights.llm import LLMClient
from bts.insights.prompts import recap_system, recap_user
from bts.insights.schemas import Insight, Lang, Profile, Recap
from bts.insights.verifier import verify
from bts.sim.models import Event
from bts.stats.moments import Moment
from bts.stats.state import StatsSnapshot

log = logging.getLogger(__name__)

CacheKey = tuple[str, str, str]


class InsightProducer(Protocol):
    """What the agent crew offers; tried before the simple pipeline when present."""

    async def for_moment(
        self,
        moment: Moment,
        snap: StatsSnapshot,
        recent: list[Event],
        profile: Profile,
        lang: Lang,
    ) -> Insight: ...

    async def recap(
        self, snap: StatsSnapshot, moments: list[Moment], profile: Profile, lang: Lang
    ) -> Recap: ...


class InsightService:
    """Crew first (when configured), then explain → verify → retry once, then the template."""

    def __init__(self, llm: LLMClient, crew: InsightProducer | None = None) -> None:
        self.llm = llm
        self.crew = crew
        self._tasks: dict[CacheKey, asyncio.Task[Insight]] = {}

    async def for_moment(
        self,
        moment: Moment,
        snap: StatsSnapshot,
        recent: list[Event],
        profile: Profile,
        lang: Lang,
    ) -> Insight:
        key: CacheKey = (moment.moment_id, profile, lang)
        task = self._tasks.get(key)
        if task is None:
            task = asyncio.create_task(self._compute(moment, snap, recent, profile, lang))
            self._tasks[key] = task
        return await task

    def cached(self, moment_id: str, profile: Profile, lang: Lang) -> Insight | None:
        task = self._tasks.get((moment_id, profile, lang))
        if task is not None and task.done() and not task.cancelled() and task.exception() is None:
            return task.result()
        return None

    async def _compute(
        self,
        moment: Moment,
        snap: StatsSnapshot,
        recent: list[Event],
        profile: Profile,
        lang: Lang,
    ) -> Insight:
        if self.crew is not None:
            try:
                return await self.crew.for_moment(moment, snap, recent, profile, lang)
            except Exception as exc:  # noqa: BLE001 - the simple pipeline is the recovery path
                log.warning(
                    "crew failed for %s (%s); using the simple pipeline", moment.moment_id, exc
                )
        issues: list[str] | None = None
        for attempt in range(2):
            try:
                insight = await explain(self.llm, moment, snap, recent, profile, lang, issues)
            except Exception as exc:  # noqa: BLE001 - any model failure degrades to a template
                log.warning(
                    "explainer failed (%s/%s) for %s: %s", attempt + 1, 2, moment.moment_id, exc
                )
                issues = None
                continue
            result = await verify(self.llm, insight, snap, moment)
            if result.ok:
                insight.verified = not any(
                    i.startswith("verifier_unavailable") for i in result.issues
                )
                return insight
            issues = result.issues
            log.info(
                "insight rejected (%s/%s) for %s: %s", attempt + 1, 2, moment.moment_id, issues
            )
        return templates.render_insight(moment, snap, profile, lang)

    async def recap(
        self, snap: StatsSnapshot, moments: list[Moment], profile: Profile, lang: Lang
    ) -> Recap:
        if self.crew is not None:
            try:
                return await self.crew.recap(snap, moments, profile, lang)
            except Exception as exc:  # noqa: BLE001 - the simple pipeline is the recovery path
                log.warning("crew recap failed (%s); using the simple pipeline", exc)
        try:
            out: RecapOutput = await self.llm.complete_json(
                system=recap_system(profile, lang),
                user=recap_user(snap, moments, profile, lang),
                schema=RecapOutput,
            )
        except Exception as exc:  # noqa: BLE001 - any model failure degrades to a template
            log.warning("recap failed: %s", exc)
            return templates.render_recap(snap, moments, profile, lang)
        return recap_from_output(out, snap, moments, profile, lang)
