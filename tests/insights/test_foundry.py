import os

import pytest

from bts.config import Settings, get_settings
from bts.insights.foundry import FoundryClient, make_llm
from bts.insights.llm import FakeLLM
from bts.insights.verifier import ExplainerOutput


def test_make_llm_without_endpoint_is_fake(monkeypatch):
    monkeypatch.delenv("BTS_FOUNDRY_ENDPOINT", raising=False)
    assert isinstance(make_llm(Settings(_env_file=None)), FakeLLM)


def test_make_llm_with_endpoint_is_foundry():
    settings = Settings(
        _env_file=None,
        foundry_endpoint="https://x.openai.azure.com/openai/v1/",
        foundry_api_key="k",
    )
    assert isinstance(make_llm(settings), FoundryClient)


@pytest.mark.skipif(not os.getenv("BTS_FOUNDRY_ENDPOINT"), reason="needs a Foundry endpoint")
async def test_foundry_round_trip():
    out = await FoundryClient(get_settings()).complete_json(
        system="Reply with JSON that fits the schema.",
        user="headline: 'Hi', why_it_matters: 'Because.', evidence: [], confidence: 0.5",
        schema=ExplainerOutput,
    )
    assert isinstance(out, ExplainerOutput)


class _Incomplete:
    status = "incomplete"
    output_parsed = None

    class incomplete_details:
        reason = "max_output_tokens"


async def test_incomplete_response_raises_llm_error_with_reason(monkeypatch):
    from bts.insights.foundry import LLMError

    settings = Settings(
        _env_file=None,
        foundry_endpoint="https://x.openai.azure.com/openai/v1/",
        foundry_api_key="k",
    )
    client = FoundryClient(settings)

    class _Responses:
        async def parse(self, **kwargs):
            return _Incomplete()

    class _Scoped:
        responses = _Responses()

    monkeypatch.setattr(client._client, "with_options", lambda **kw: _Scoped())
    with pytest.raises(LLMError, match="max_output_tokens"):
        await client.complete_json(system="s", user="u", schema=ExplainerOutput)


def _live_settings(**overrides) -> Settings:
    base = {"foundry_endpoint": "https://x.openai.azure.com/openai/v1/", "foundry_api_key": "k"}
    return Settings(_env_file=None, **{**base, **overrides})


def test_make_crew_is_none_without_endpoint(monkeypatch):
    from bts.insights.foundry import make_crew

    monkeypatch.delenv("BTS_FOUNDRY_ENDPOINT", raising=False)
    assert make_crew(Settings(_env_file=None)) is None


def test_make_crew_defaults_to_crew_mode_with_a_key():
    from bts.insights.crew.crew import AgentCrew
    from bts.insights.foundry import make_crew

    factory = make_crew(_live_settings())
    assert factory is not None
    a, b = factory(), factory()
    assert isinstance(a, AgentCrew) and a is not b and a.client is b.client


def test_make_crew_respects_simple_mode_and_missing_key():
    from bts.insights.foundry import make_crew

    assert make_crew(_live_settings(agent_mode="simple")) is None
    assert make_crew(_live_settings(foundry_api_key=None, agent_mode="crew")) is None


def test_make_qa_follows_the_flag_and_the_crew(monkeypatch):
    from bts.insights.foundry import make_qa
    from bts.insights.qa.agent import QAAgent

    assert isinstance(make_qa(_live_settings()), QAAgent)  # unset flag, crew on
    assert make_qa(_live_settings(qa_enabled=False)) is None
    assert make_qa(_live_settings(agent_mode="simple")) is None  # unset flag, crew off
    assert isinstance(make_qa(_live_settings(agent_mode="simple", qa_enabled=True)), QAAgent)
    assert make_qa(_live_settings(foundry_api_key=None, qa_enabled=True)) is None
    monkeypatch.delenv("BTS_FOUNDRY_ENDPOINT", raising=False)
    assert make_qa(Settings(_env_file=None, qa_enabled=True)) is None


def test_settings_read_qa_enabled(monkeypatch):
    monkeypatch.setenv("BTS_QA_ENABLED", "false")
    assert Settings(_env_file=None).qa_enabled is False
    monkeypatch.setenv("BTS_QA_ENABLED", "")
    assert Settings(_env_file=None).qa_enabled is None
