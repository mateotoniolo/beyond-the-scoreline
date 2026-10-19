"""The crew: one tactical analysis per moment, then narrate → fact-check → produce.

The analysis is an Agent Framework ``Agent`` run with tools over the shared match context.
Narration, checking and production run as a ``SequentialBuilder`` workflow whose whole
conversation flows from role to role; a rejected draft goes back to the narrator once with
the issues attached, and a second rejection ships the template. Every model turn is bounded
by a timeout; failures raise ``CrewError`` so the caller can fall back.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from time import perf_counter
from typing import TypeVar

from agent_framework import Agent, Executor, Message
from agent_framework.openai import OpenAIChatClient
from agent_framework.orchestrations import SequentialBuilder
from pydantic import BaseModel

from bts.config import Settings
from bts.insights import templates
from bts.insights.crew import prompts
from bts.insights.crew.agents import (
    FACT_CHECKER,
    NARRATOR,
    PRODUCER,
    Analysis,
    make_analyst,
    make_chat_client,
    make_fact_checker,
    make_narrator,
    make_recap_narrator,
)
from bts.insights.crew.context import MatchContext
from bts.insights.crew.producer import Producer, ProducerOutput, count_tool_calls
from bts.insights.explainer import RecapOutput, recap_from_output, to_insight
from bts.insights.prompts import explainer_user, recap_user
from bts.insights.schemas import AgentStep, Insight, Lang, Profile, Recap
from bts.sim.models import Event
from bts.stats.moments import Moment
from bts.stats.state import StatsSnapshot

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

AGENT_TIMEOUT_S = 20.0
WORKFLOW_TIMEOUT_S = 45.0
MAX_PASSES = 2
TRACKED = frozenset({NARRATOR, FACT_CHECKER, PRODUCER})


class CrewError(Exception):
    """The crew could not deliver; the caller falls back to the simple pipeline."""


class AgentCrew:
    def __init__(
        self,
        client: OpenAIChatClient,
        model: str,
        *,
        agent_timeout_s: float = AGENT_TIMEOUT_S,
        workflow_timeout_s: float = WORKFLOW_TIMEOUT_S,
    ) -> None:
        self.client = client
        self.model = model
        self.agent_timeout_s = agent_timeout_s
        self.workflow_timeout_s = workflow_timeout_s
        self._analyses: dict[str, asyncio.Task[tuple[Analysis, AgentStep]]] = {}

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: float) -> AgentCrew:
        return cls(make_chat_client(settings), settings.foundry_model, **kwargs)

    # ------------------------------------------------------------------ public contract
    async def for_moment(
        self,
        moment: Moment,
        snap: StatsSnapshot,
        recent: list[Event],
        profile: Profile,
        lang: Lang,
    ) -> Insight:
        ctx = MatchContext(moment, snap, recent)
        analysis, analyst_step = await self.analyse(ctx)
        trace = [analyst_step]
        conversation: list[Message] = [Message("user", [prompts.narration_brief(ctx, analysis)])]
        for attempt in range(MAX_PASSES):
            participants = [
                make_narrator(self.client, profile, lang),
                make_fact_checker(self.client, ctx),
                Producer(ctx, profile, lang),
            ]
            out, steps = await self._run_workflow(participants, conversation)
            trace.extend(steps)
            if out.ok and out.draft is not None:
                insight = to_insight(out.draft, moment, profile, lang)
                insight.verified = not any(i.startswith("verifier_unavailable") for i in out.issues)
                insight.trace = trace
                return insight
            log.info(
                "crew rejected draft (%s/%s) for %s: %s",
                attempt + 1,
                MAX_PASSES,
                moment.moment_id,
                out.issues,
            )
            conversation = [*out.conversation, Message("user", [prompts.retry_brief(out.issues)])]
        insight = templates.render_insight(moment, snap, profile, lang)
        insight.trace = trace
        return insight

    async def recap(
        self, snap: StatsSnapshot, moments: list[Moment], profile: Profile, lang: Lang
    ) -> Recap:
        agent = make_recap_narrator(self.client, profile, lang)
        out, _ = await self._run_agent(agent, recap_user(snap, moments, profile, lang), RecapOutput)
        return recap_from_output(out, snap, moments, profile, lang)

    async def analyse(self, ctx: MatchContext) -> tuple[Analysis, AgentStep]:
        """The tactical analysis, computed once per moment and shared by every variant."""
        key = ctx.moment.moment_id
        task = self._analyses.get(key)
        if task is None:
            task = asyncio.create_task(self._analyse(ctx))
            self._analyses[key] = task
        try:
            return await task
        except BaseException:
            self._analyses.pop(key, None)  # let a later request try again
            raise

    async def _analyse(self, ctx: MatchContext) -> tuple[Analysis, AgentStep]:
        brief = explainer_user(ctx.moment, ctx.snap, ctx.recent)
        return await self._run_agent(make_analyst(self.client, ctx), brief, Analysis)

    # ------------------------------------------------------------------ model seams
    async def _run_agent(
        self, agent: Agent, message: str, response_format: type[T]
    ) -> tuple[T, AgentStep]:
        t0 = perf_counter()
        try:
            response = await asyncio.wait_for(agent.run(message), self.agent_timeout_s)
        except TimeoutError as exc:
            raise CrewError(f"{agent.name} timed out after {self.agent_timeout_s:.0f}s") from exc
        except Exception as exc:
            raise CrewError(f"{agent.name} failed: {type(exc).__name__}: {exc}") from exc
        value = response.value
        if not isinstance(value, response_format):
            raise CrewError(f"{agent.name} returned no {response_format.__name__}")
        step = AgentStep(
            agent=agent.name or "agent",
            ms=max(1, int((perf_counter() - t0) * 1000)),
            tool_calls=count_tool_calls(response.messages),
        )
        return value, step

    async def _run_workflow(
        self, participants: Sequence[Agent | Executor], conversation: Sequence[Message]
    ) -> tuple[ProducerOutput, list[AgentStep]]:
        workflow = SequentialBuilder(participants=list(participants)).build()
        steps: list[AgentStep] = []
        started: dict[str, float] = {}

        async def consume():
            stream = workflow.run(list(conversation), stream=True)
            async for event in stream:
                executor_id = event.executor_id
                if executor_id not in TRACKED:
                    continue
                kind = str(event.type).lower()
                if kind.endswith("executor_invoked"):
                    started[executor_id] = perf_counter()
                elif kind.endswith("executor_completed") and executor_id in started:
                    ms = max(1, int((perf_counter() - started.pop(executor_id)) * 1000))
                    steps.append(AgentStep(agent=executor_id, ms=ms))
            return await stream.get_final_response()

        try:
            result = await asyncio.wait_for(consume(), self.workflow_timeout_s)
        except TimeoutError as exc:
            raise CrewError(
                f"crew workflow timed out after {self.workflow_timeout_s:.0f}s"
            ) from exc
        except Exception as exc:
            raise CrewError(f"crew workflow failed: {type(exc).__name__}: {exc}") from exc
        outputs = [o for o in result.get_outputs() if isinstance(o, ProducerOutput)]
        if not outputs:
            raise CrewError("the producer yielded no output")
        out = outputs[-1]
        for step in steps:
            step.tool_calls = out.tool_calls.get(step.agent, 0)
        return out, steps
