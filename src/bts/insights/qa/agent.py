"""The question desk: one Agent Framework agent with tools over the live match.

One bounded run per question. Every cited number is re-checked against the current statistics
before the reply is marked verified; any failure returns a deterministic bilingual fallback.
The last few exchanges per conversation stay in memory (never persisted) and are sent as
prior messages so follow-up questions read naturally.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections import OrderedDict
from time import perf_counter

from agent_framework import Agent, Message
from agent_framework.openai import OpenAIChatClient

from bts.config import Settings
from bts.insights.crew.agents import make_chat_client, model_options
from bts.insights.crew.producer import count_tool_calls
from bts.insights.qa import prompts
from bts.insights.qa.checker import check_citations
from bts.insights.qa.context import LiveMatch, QAContext
from bts.insights.qa.schemas import FALLBACK, AskResult, QAAnswer
from bts.insights.schemas import AgentStep, Lang, Profile

log = logging.getLogger(__name__)

QA_AGENT = "match_qa"
TIMEOUT_S = 20.0
MEMORY_MESSAGES = 6  # three exchanges
MAX_CONVERSATIONS = 256

ConversationKey = tuple[str, str]


class QAError(Exception):
    """The agent returned no usable answer."""


def make_qa_agent(client: OpenAIChatClient, ctx: QAContext, profile: Profile, lang: Lang) -> Agent:
    return Agent(
        client=client,
        name=QA_AGENT,
        instructions=prompts.qa_instructions(profile, lang),
        tools=ctx.tools(),
        default_options=model_options(QAAnswer, client.model),
    )


class QAAgent:
    def __init__(
        self, client: OpenAIChatClient, model: str, *, timeout_s: float = TIMEOUT_S
    ) -> None:
        self.client = client
        self.model = model
        self.timeout_s = timeout_s
        self._memory: OrderedDict[ConversationKey, list[Message]] = OrderedDict()

    @classmethod
    def from_settings(cls, settings: Settings, **kwargs: float) -> QAAgent:
        return cls(make_chat_client(settings), settings.foundry_model, **kwargs)

    # ------------------------------------------------------------------ public contract
    def history(self, match_id: str, conversation_id: str) -> list[Message]:
        return list(self._memory.get((match_id, conversation_id), []))

    async def ask(
        self,
        match: LiveMatch,
        question: str,
        profile: Profile,
        lang: Lang,
        conversation_id: str | None = None,
    ) -> AskResult:
        conversation_id = conversation_id or secrets.token_hex(4)
        key: ConversationKey = (match.match_id, conversation_id)
        ctx = QAContext(match, profile, lang)
        agent = make_qa_agent(self.client, ctx, profile, lang)
        messages = [*self.history(*key), Message("user", [prompts.question_brief(ctx, question)])]
        t0 = perf_counter()
        try:
            answer, step = await asyncio.wait_for(self._run(agent, messages), self.timeout_s)
        except Exception as exc:  # noqa: BLE001 - every failure degrades to the fallback
            ms = max(1, int((perf_counter() - t0) * 1000))
            log.warning("qa failed for %s after %sms: %s: %s", key, ms, type(exc).__name__, exc)
            return AskResult(
                conversation_id=conversation_id,
                answer=FALLBACK[lang],
                verified=False,
                grounded=False,
                source="template",
                trace=[AgentStep(agent=QA_AGENT, ms=ms, ok=False)],
            )
        issues = check_citations(answer.citations, ctx.snap, match.moments, match.meta, ctx.served)
        verified = answer.grounded and bool(answer.citations) and not issues
        if issues:
            log.info("qa citations rejected for %s: %s", key, issues)
        self._remember(key, question, answer.answer)
        log.info(
            "qa answered %s in %sms (tools=%s verified=%s grounded=%s)",
            key,
            step.ms,
            step.tool_calls,
            verified,
            answer.grounded,
        )
        return AskResult(
            conversation_id=conversation_id,
            answer=answer.answer,
            citations=answer.citations,
            verified=verified,
            grounded=answer.grounded,
            source="llm",
            trace=[step],
        )

    # ------------------------------------------------------------------ model seam
    async def _run(self, agent: Agent, messages: list[Message]) -> tuple[QAAnswer, AgentStep]:
        t0 = perf_counter()
        response = await agent.run(messages)
        value = response.value
        if not isinstance(value, QAAnswer):
            raise QAError(f"{agent.name} returned no {QAAnswer.__name__}")
        step = AgentStep(
            agent=agent.name or QA_AGENT,
            ms=max(1, int((perf_counter() - t0) * 1000)),
            tool_calls=count_tool_calls(response.messages),
        )
        return value, step

    # ------------------------------------------------------------------ memory
    def _remember(self, key: ConversationKey, question: str, answer: str) -> None:
        turns = self._memory.get(key, [])
        turns = [*turns, Message("user", [question]), Message("assistant", [answer])]
        self._memory[key] = turns[-MEMORY_MESSAGES:]
        self._memory.move_to_end(key)
        while len(self._memory) > MAX_CONVERSATIONS:
            self._memory.popitem(last=False)
