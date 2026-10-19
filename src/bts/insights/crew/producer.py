"""The producer: the deterministic last participant of the crew (no model involved).

It turns the narrator's draft and the fact checker's verdict into a decision, re-running the
numeric checks itself, and plans overlay cues that never overlap on screen.
"""

import inspect
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Never

from agent_framework import AgentExecutorResponse, Executor, Message, WorkflowContext, handler
from pydantic import BaseModel, ValidationError

from bts.insights.crew.agents import FACT_CHECKER, NARRATOR, PRODUCER
from bts.insights.crew.context import MatchContext
from bts.insights.cues import from_insight
from bts.insights.explainer import to_insight
from bts.insights.schemas import Cue, Insight, Lang, Profile
from bts.insights.verifier import NON_ISSUE_RE, ExplainerOutput, VerifierOutput, check_facts
from bts.stats.moments import Moment

# Goals and red cards take the lower third at once instead of waiting their turn.
PREEMPT_SEVERITY = 0.9
VERIFIER_UNAVAILABLE = "verifier_unavailable: the fact checker reply is not a verdict"


@dataclass
class ProducerOutput:
    draft: ExplainerOutput | None
    ok: bool
    issues: list[str]
    tool_calls: dict[str, int] = field(default_factory=dict)
    conversation: list[Message] = field(default_factory=list)


def count_tool_calls(messages: Sequence[Any]) -> int:
    return sum(
        1
        for m in messages
        for c in getattr(m, "contents", ())
        if getattr(c, "type", None) == "function_call"
    )


def _last_text(conversation: Sequence[Message], author: str) -> str | None:
    for m in reversed(conversation):
        if m.author_name == author and m.role == "assistant" and (m.text or "").strip():
            return m.text
    return None


def _parse[T: BaseModel](model: type[T], text: str | None) -> T | None:
    if not text:
        return None
    cleaned = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    try:
        return model.model_validate_json(cleaned)
    except (ValidationError, ValueError):
        return None


def produce(
    conversation: Sequence[Message],
    tool_calls: dict[str, int],
    ctx: MatchContext,
    profile: Profile,
    lang: Lang,
) -> ProducerOutput:
    """Decide on the narrator's draft: deterministic numeric checks first, then the verdict."""
    history = list(conversation)
    draft = _parse(ExplainerOutput, _last_text(history, NARRATOR))
    if draft is None:
        issues = ["the narrator reply is not a valid insight"]
        return ProducerOutput(None, False, issues, tool_calls, history)
    insight = to_insight(draft, ctx.moment, profile, lang)
    issues = check_facts(insight, ctx.snap, ctx.moment)
    if issues:
        return ProducerOutput(draft, False, issues, tool_calls, history)
    verdict = _parse(VerifierOutput, _last_text(history, FACT_CHECKER))
    if verdict is None:
        return ProducerOutput(draft, True, [VERIFIER_UNAVAILABLE], tool_calls, history)
    contradictions = (
        []
        if verdict.ok
        else [i for i in verdict.issues if i.strip() and not NON_ISSUE_RE.search(i)]
    )
    return ProducerOutput(draft, not contradictions, contradictions, tool_calls, history)


class Producer(Executor):
    """Terminal participant of the narrate → check → produce workflow."""

    def __init__(self, ctx: MatchContext, profile: Profile, lang: Lang) -> None:
        super().__init__(id=PRODUCER)
        self.match = ctx
        self.profile = profile
        self.lang = lang

    @handler
    async def on_response(
        self, response: AgentExecutorResponse, ctx: WorkflowContext[Never, ProducerOutput]
    ) -> None:
        calls = {response.executor_id: count_tool_calls(response.agent_response.messages)}
        out = produce(response.full_conversation, calls, self.match, self.profile, self.lang)
        result = ctx.yield_output(out)
        if inspect.isawaitable(result):
            await result


# ---------------------------------------------------------------------------- cue planning
# A new cue waits for the running one when the wait is short; otherwise it takes the layer
# and the running cue is cut (queued cues that never started are dropped with duration 0).
MAX_WAIT_S = 10.0


def _end(cue: Cue, factor: float) -> float:
    """Match-time end of a cue: ``duration_s`` is in real seconds, hence the speed factor."""
    return cue.t_start + cue.duration_s * factor


def plan_cues(
    insight: Insight, moment: Moment, existing: list[Cue], speed: float = 1.0
) -> list[Cue]:
    """Cues for ``insight`` that never overlap ``existing`` cues on the same layer.

    Waiting more than ``MAX_WAIT_S`` real seconds, or a severe moment (a goal, a red card)
    on the lower third, preempts instead: the running cue comes back with its duration cut,
    under the same ``cue_id``, so clients replace it.
    """
    factor = max(1.0, speed)
    planned: list[Cue] = []
    replaced: list[Cue] = []
    for cue in from_insight(insight, moment):
        same_layer = [c for c in existing if c.layer == cue.layer and c.duration_s > 0]
        queue_end = max((_end(c, factor) for c in same_layer), default=cue.t_start)
        wait_s = (queue_end - cue.t_start) / factor
        preempt = moment.severity >= PREEMPT_SEVERITY and cue.layer == "lower_third"
        if wait_s <= 0:
            planned.append(cue)
        elif wait_s <= MAX_WAIT_S and not preempt:
            planned.append(cue.model_copy(update={"t_start": queue_end}))
        else:
            for prev in same_layer:
                if _end(prev, factor) <= cue.t_start:
                    continue
                shorter = max(0.0, (cue.t_start - prev.t_start) / factor)
                replaced.append(prev.model_copy(update={"duration_s": shorter}))
            planned.append(cue)
    return planned + replaced
