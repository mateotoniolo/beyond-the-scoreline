import asyncio
import os
import time

import pytest

from bts.config import Settings, get_settings
from bts.insights.qa.agent import MEMORY_MESSAGES, QA_AGENT, QAAgent, make_qa_agent
from bts.insights.qa.context import QAContext
from bts.insights.qa.schemas import FALLBACK, QAAnswer
from bts.insights.schemas import AgentStep, Evidence


def _qa(**kwargs) -> QAAgent:
    settings = Settings(
        _env_file=None,
        foundry_endpoint="https://x.openai.azure.com/openai/v1/",
        foundry_api_key="k",
    )
    return QAAgent.from_settings(settings, **kwargs)


def _answer(live, *, value: str | None = None, grounded: bool = True, citations=True):
    snap = live.snapshot()
    home = snap.team_names[snap.home_id]
    cited = [Evidence(stat="xg", value=value or f"{home} {snap.teams[snap.home_id].xg:.2f}")]
    return QAAnswer(
        answer=f"{home} lead on xG.",
        citations=cited if citations else [],
        confidence=0.8,
        grounded=grounded,
    )


def _script(qa: QAAgent, answer: QAAnswer, *, tool_calls: int = 2) -> list[list]:
    seen: list[list] = []

    async def run(agent, messages):
        seen.append(list(messages))
        return answer, AgentStep(agent=agent.name, ms=3100, tool_calls=tool_calls)

    qa._run = run
    return seen


async def test_happy_path_is_verified_and_remembered(live):
    qa = _qa()
    seen = _script(qa, _answer(live))
    out = await qa.ask(live, "Who leads on xG?", "analyst", "en")
    assert (out.source, out.verified, out.grounded) == ("llm", True, True)
    assert out.conversation_id and out.answer.endswith("lead on xG.")
    assert [(s.agent, s.tool_calls, s.ok) for s in out.trace] == [(QA_AGENT, 2, True)]
    first = seen[0]
    assert len(first) == 1 and first[0].role == "user"
    assert "Who leads on xG?" in first[0].text and '"score"' in first[0].text
    again = await qa.ask(live, "And on shots?", "analyst", "en", out.conversation_id)
    assert again.conversation_id == out.conversation_id
    second = seen[1]
    assert [m.role for m in second] == ["user", "assistant", "user"]
    assert second[0].text == "Who leads on xG?" and second[1].text == out.answer
    assert "And on shots?" in second[2].text


async def test_memory_keeps_six_messages_per_conversation(live):
    qa = _qa()
    seen = _script(qa, _answer(live))
    first = await qa.ask(live, "q1", "fan", "es")
    for i in range(2, 6):
        await qa.ask(live, f"q{i}", "fan", "es", first.conversation_id)
    history = qa.history(live.match_id, first.conversation_id)
    assert len(history) == MEMORY_MESSAGES and history[0].text == "q3"
    assert len(seen[-1]) == MEMORY_MESSAGES + 1
    assert seen[-1][0].text == "q2"  # the fifth question carried exchanges two to four
    other = await qa.ask(live, "fresh", "fan", "es")
    assert other.conversation_id != first.conversation_id
    assert len(seen[-1]) == 1
    assert qa.history("another-match", first.conversation_id) == []


async def test_citations_are_checked_against_the_board_the_question_saw(live):
    qa = _qa()
    snap = live.snapshot()
    home = snap.team_names[snap.home_id]
    cited = QAAnswer(
        answer="Passes so far.",
        citations=[Evidence(stat="passes", value=f"{home} {snap.teams[snap.home_id].passes}")],
        confidence=0.9,
        grounded=True,
    )

    async def run(agent, messages):
        live.advance(300)  # the match moves on while the model answers
        return cited, AgentStep(agent=agent.name, ms=2000, tool_calls=1)

    qa._run = run
    assert live.snapshot().teams[snap.home_id].passes == snap.teams[snap.home_id].passes
    out = await qa.ask(live, "How many passes?", "analyst", "en")
    assert live.snapshot().teams[snap.home_id].passes > snap.teams[snap.home_id].passes + 1
    assert out.verified is True


async def test_numbers_served_by_get_insight_verify(live):
    from bts.insights import templates

    qa = _qa()
    snap = live.snapshot()
    away = snap.team_names[snap.away_id]
    goal = next(m for m in live.moments if m.type == "goal")
    old_board = templates.render_insight(goal, snap, "analyst", "en").model_copy(
        update={"evidence": [Evidence(stat="xg", value="9.99")]}
    )
    live.insights[(goal.moment_id, "analyst", "en")] = old_board
    cited = QAAnswer(
        answer="At the goal their xG stood at 9.99.",
        citations=[Evidence(stat="xg", value=f"{away} 9.99")],
        confidence=0.9,
        grounded=True,
    )

    async def run(agent, messages):
        get_insight = next(t for t in agent.default_options["tools"] if t.name == "get_insight")
        assert "9.99" in get_insight.func(moment_id=goal.moment_id)
        return cited, AgentStep(agent=agent.name, ms=2000, tool_calls=1)

    qa._run = run
    out = await qa.ask(live, "What was their xG at the goal?", "analyst", "en")
    assert out.verified is True


async def test_failed_citation_is_unverified_but_kept(live):
    qa = _qa()
    _script(qa, _answer(live, value="999.9"))
    out = await qa.ask(live, "xG?", "analyst", "en")
    assert out.source == "llm" and out.verified is False and out.grounded is True
    assert out.citations[0].value == "999.9"


async def test_ungrounded_or_uncited_answers_are_never_verified(live):
    qa = _qa()
    _script(qa, _answer(live, grounded=False))
    out = await qa.ask(live, "Who will win?", "analyst", "en")
    assert out.verified is False and out.grounded is False and out.source == "llm"
    _script(qa, _answer(live, citations=False))
    out = await qa.ask(live, "Any goals?", "analyst", "en")
    assert out.verified is False and out.grounded is True


async def test_timeout_returns_template_fallback(live):
    qa = _qa(timeout_s=0.05)

    async def slow(agent, messages):
        await asyncio.sleep(1)

    qa._run = slow
    out = await qa.ask(live, "¿Quién domina?", "fan", "es")
    assert out.answer == FALLBACK["es"] and out.source == "template"
    assert out.verified is False and out.grounded is False and out.citations == []
    assert len(out.trace) == 1 and out.trace[0].agent == QA_AGENT and out.trace[0].ok is False
    assert out.trace[0].ms >= 1
    assert qa.history(live.match_id, out.conversation_id) == []


async def test_run_error_returns_fallback(live):
    qa = _qa()

    async def boom(agent, messages):
        raise RuntimeError("boom")

    qa._run = boom
    out = await qa.ask(live, "Score?", "analyst", "en")
    assert out.answer == FALLBACK["en"] and out.source == "template"


def test_qa_agent_has_tools_and_language(live):
    settings = Settings(
        _env_file=None,
        foundry_endpoint="https://x.openai.azure.com/openai/v1/",
        foundry_api_key="k",
    )
    from bts.insights.crew.agents import make_chat_client

    client = make_chat_client(settings)
    agent = make_qa_agent(client, QAContext(live, "fan", "es"), "fan", "es")
    assert agent.name == QA_AGENT
    assert len(agent.default_options["tools"]) == 11
    assert agent.default_options["response_format"] is QAAnswer
    instructions = agent.default_options["instructions"]
    assert "Spanish" in instructions and "grounded" in instructions


@pytest.mark.skipif(not os.getenv("BTS_FOUNDRY_ENDPOINT"), reason="needs a Foundry endpoint")
async def test_qa_live_round_trip(live):
    qa = QAAgent.from_settings(get_settings())
    t0 = time.perf_counter()
    out = await qa.ask(live, "Who is creating the most chances?", "analyst", "en")
    elapsed = time.perf_counter() - t0
    print(f"\nlive qa: {elapsed:.1f}s source={out.source} verified={out.verified}")
    print("answer:", out.answer)
    print("citations:", [(c.stat, c.value) for c in out.citations])
    print("trace:", [(s.agent, s.ms, s.tool_calls) for s in out.trace])
    assert out.source == "llm" and out.grounded
