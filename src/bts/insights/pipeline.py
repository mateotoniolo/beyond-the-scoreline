"""Explain → verify → retry once → template. Never blocks the event stream."""

from __future__ import annotations

import asyncio
import logging

from bts.insights import templates
from bts.insights.explainer import RecapOutput, explain
from bts.insights.llm import LLMClient, LLMError
from bts.insights.prompts import recap_system, recap_user
from bts.insights.schemas import Insight, Lang, Profile, Recap
from bts.insights.verifier import verify
from bts.sim.models import Event
from bts.stats.moments import Moment
from bts.stats.state import StatsSnapshot

log = logging.getLogger(__name__)

CacheKey = tuple[str, str, str]


class InsightService:
    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
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
        issues: list[str] | None = None
        for attempt in range(2):
            try:
                insight = await explain(self.llm, moment, snap, recent, profile, lang, issues)
            except LLMError as exc:
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
        try:
            out: RecapOutput = await self.llm.complete_json(
                system=recap_system(profile, lang),
                user=recap_user(snap, moments, profile, lang),
                schema=RecapOutput,
            )
        except LLMError as exc:
            log.warning("recap failed: %s", exc)
            return templates.render_recap(snap, moments, profile, lang)
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
