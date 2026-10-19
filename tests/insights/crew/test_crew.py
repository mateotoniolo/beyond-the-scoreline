import asyncio
import json
import os
import time

import pytest
from agent_framework import Agent, Executor, Message

from bts.config import Settings, get_settings
from bts.insights.crew.agents import ANALYST, FACT_CHECKER, NARRATOR, PRODUCER, Analysis
from bts.insights.crew.context import MatchContext
from bts.insights.crew.crew import AgentCrew, CrewError
from bts.insights.crew.producer import ProducerOutput, produce
from bts.insights.schemas import AgentStep, Evidence
from bts.insights.verifier import ExplainerOutput, VerifierOutput


def _crew(**kwargs) -> AgentCrew:
    settings = Settings(
        _env_file=None,
        foundry_endpoint="https://x.openai.azure.com/openai/v1/",
        foundry_api_key="k",
    )
    return AgentCrew.from_settings(settings, **kwargs)


def _analysis(snap, moment) -> Analysis:
    team = snap.team_names[moment.team_id]
    xg = snap.teams[moment.team_id].xg
    return Analysis(
        pattern=f"{team} sustained pressure",
        key_numbers=[Evidence(stat="xg", value=f"{team} {xg:.2f}")],
        confidence=0.8,
    )


def _draft(snap, moment, *, value: str | None = None) -> ExplainerOutput:
    xg = value or f"{snap.teams[moment.team_id].xg:.2f}"
    return ExplainerOutput(
        headline="Pressure finally told",
        why_it_matters="Their xG kept climbing and the goal followed.",
        evidence=[Evidence(stat="xg", value=xg)],
        confidence=0.7,
    )


def _output(draft, ok, issues=(), conversation=()) -> ProducerOutput:
    return ProducerOutput(
        draft=draft,
        ok=ok,
        issues=list(issues),
        tool_calls={FACT_CHECKER: 1},
        conversation=list(conversation),
    )


def _steps() -> list[AgentStep]:
    return [
        AgentStep(agent=NARRATOR, ms=1400),
        AgentStep(agent=FACT_CHECKER, ms=1200),
        AgentStep(agent=PRODUCER, ms=1),
    ]


class _Scripted:
    """Stands in for the two model seams: scripted analysis and workflow outputs."""

    def __init__(self, crew: AgentCrew, analysis: Analysis, outputs: list[ProducerOutput]):
        self.agent_runs = 0
        self.workflow_calls: list[tuple[list[str], list[Message]]] = []
        self._analysis = analysis
        self._outputs = outputs

        async def run_agent(agent, message, response_format):
            self.agent_runs += 1
            return self._analysis, AgentStep(agent=agent.name, ms=2100, tool_calls=0)

        async def run_workflow(participants, conversation):
            names = [p.id if isinstance(p, Executor) else p.name for p in participants]
            self.workflow_calls.append((names, list(conversation)))
            out = self._outputs.pop(0)
            out.conversation = [
                *conversation,
                Message("assistant", ["draft"], author_name=NARRATOR),
            ]
            return out, _steps()

        crew._run_agent = run_agent
        crew._run_workflow = run_workflow


async def test_happy_path_runs_four_roles_and_verifies(moment, snap, recent):
    crew = _crew()
    script = _Scripted(crew, _analysis(snap, moment), [_output(_draft(snap, moment), True)])
    insight = await crew.for_moment(moment, snap, recent, "analyst", "en")
    assert (insight.source, insight.verified) == ("llm", True)
    assert insight.headline == "Pressure finally told"
    assert [s.agent for s in insight.trace] == [ANALYST, NARRATOR, FACT_CHECKER, PRODUCER]
    names, conversation = script.workflow_calls[0]
    assert names == [NARRATOR, FACT_CHECKER, PRODUCER]
    assert len(conversation) == 1 and "sustained pressure" in conversation[0].text


async def test_double_rejection_ships_template_with_trace(moment, snap, recent):
    crew = _crew()
    rejected = [_output(_draft(snap, moment), False, ["xg is wrong"]) for _ in range(2)]
    script = _Scripted(crew, _analysis(snap, moment), rejected)
    insight = await crew.for_moment(moment, snap, recent, "fan", "es")
    assert (insight.source, insight.verified) == ("template", False)
    assert [s.agent for s in insight.trace] == [ANALYST, *([NARRATOR, FACT_CHECKER, PRODUCER] * 2)]
    _, retry_conversation = script.workflow_calls[1]
    assert retry_conversation[-1].role == "user" and "xg is wrong" in retry_conversation[-1].text
    assert any(m.author_name == NARRATOR for m in retry_conversation)


async def test_verifier_unavailable_ships_unverified_llm_insight(moment, snap, recent):
    crew = _crew()
    out = _output(_draft(snap, moment), True, ["verifier_unavailable: bad json"])
    _Scripted(crew, _analysis(snap, moment), [out])
    insight = await crew.for_moment(moment, snap, recent, "analyst", "en")
    assert (insight.source, insight.verified) == ("llm", False)


async def test_analysis_is_shared_across_variants(moment, snap, recent):
    crew = _crew()
    outputs = [_output(_draft(snap, moment), True) for _ in range(2)]
    script = _Scripted(crew, _analysis(snap, moment), outputs)
    await asyncio.gather(
        crew.for_moment(moment, snap, recent, "analyst", "en"),
        crew.for_moment(moment, snap, recent, "fan", "es"),
    )
    assert script.agent_runs == 1
    assert len(script.workflow_calls) == 2


async def test_agent_timeout_raises_crew_error(moment, snap, recent, monkeypatch):
    crew = _crew(agent_timeout_s=0.05)

    async def slow_run(self, *args, **kwargs):
        await asyncio.sleep(1)

    monkeypatch.setattr(Agent, "run", slow_run)
    with pytest.raises(CrewError, match="timed out"):
        await crew.for_moment(moment, snap, recent, "analyst", "en")


def _conversation(narrator_text: str | None, checker_text: str | None) -> list[Message]:
    msgs = [Message("user", ["brief"])]
    if narrator_text is not None:
        msgs.append(Message("assistant", [narrator_text], author_name=NARRATOR))
    if checker_text is not None:
        msgs.append(Message("assistant", [checker_text], author_name=FACT_CHECKER))
    return msgs


def test_produce_accepts_a_consistent_draft(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    draft = _draft(snap, moment).model_dump_json()
    verdict = VerifierOutput(ok=True, issues=[]).model_dump_json()
    out = produce(_conversation(draft, verdict), {FACT_CHECKER: 2}, ctx, "analyst", "en")
    assert out.ok and out.issues == [] and out.draft is not None
    assert out.tool_calls == {FACT_CHECKER: 2}


def test_produce_rejects_numbers_the_statistics_do_not_support(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    draft = _draft(snap, moment, value="999.9").model_dump_json()
    verdict = VerifierOutput(ok=True, issues=[]).model_dump_json()
    out = produce(_conversation(draft, verdict), {}, ctx, "analyst", "en")
    assert not out.ok and any("xg=999.9" in i for i in out.issues)


def test_produce_keeps_only_the_checker_contradictions(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    draft = _draft(snap, moment).model_dump_json()
    verdict = json.dumps({"ok": False, "issues": ["The xG matches the statistics", "Wrong team"]})
    out = produce(_conversation(draft, verdict), {}, ctx, "analyst", "en")
    assert not out.ok and out.issues == ["Wrong team"]


def test_produce_without_a_readable_verdict_is_unverified_not_rejected(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    draft = _draft(snap, moment).model_dump_json()
    out = produce(_conversation(draft, "not json"), {}, ctx, "analyst", "en")
    assert out.ok and out.issues and out.issues[0].startswith("verifier_unavailable")


def test_produce_without_a_readable_draft_is_rejected(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    out = produce(_conversation("{not json", None), {}, ctx, "fan", "en")
    assert not out.ok and out.draft is None and out.issues


@pytest.mark.skipif(not os.getenv("BTS_FOUNDRY_ENDPOINT"), reason="needs a Foundry endpoint")
async def test_crew_live_round_trip(moment, snap, recent):
    crew = AgentCrew.from_settings(get_settings())
    t0 = time.perf_counter()
    insight = await crew.for_moment(moment, snap, recent, "analyst", "en")
    elapsed = time.perf_counter() - t0
    print(f"\nlive crew: {elapsed:.1f}s source={insight.source} verified={insight.verified}")
    print("trace:", [(s.agent, s.ms, s.tool_calls) for s in insight.trace])
    print("headline:", insight.headline)
    assert insight.source == "llm"
    assert [s.agent for s in insight.trace[:4]] == [ANALYST, NARRATOR, FACT_CHECKER, PRODUCER]
    assert all(s.ms > 0 for s in insight.trace[:3])
