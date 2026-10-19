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
