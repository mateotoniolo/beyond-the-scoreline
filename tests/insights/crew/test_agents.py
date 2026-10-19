from bts.config import Settings
from bts.insights.crew.agents import (
    Analysis,
    make_analyst,
    make_chat_client,
    make_fact_checker,
    make_narrator,
    model_options,
)
from bts.insights.crew.context import MatchContext


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        foundry_endpoint="https://x.openai.azure.com/openai/v1/",
        foundry_api_key="k",
        foundry_model="gpt-5-mini",
    )


def _tool_names(agent) -> set[str]:
    return {t.name for t in agent.default_options["tools"]}


def test_chat_client_targets_the_foundry_resource():
    client = make_chat_client(_settings())
    assert client.model == "gpt-5-mini"
    assert str(client.client.base_url) == "https://x.openai.azure.com/openai/v1/"


def test_agents_have_roles_and_tools(moment, snap, recent):
    ctx = MatchContext(moment, snap, recent)
    client = make_chat_client(_settings())
    analyst = make_analyst(client, ctx)
    narrator = make_narrator(client, "fan", "es")
    checker = make_fact_checker(client, ctx)
    assert (analyst.name, narrator.name, checker.name) == (
        "tactical_analyst",
        "narrator",
        "fact_checker",
    )
    assert "check_numbers" not in _tool_names(analyst)
    assert "get_moment" in _tool_names(analyst)
    assert _tool_names(narrator) == set()
    assert "check_numbers" in _tool_names(checker)
    assert "Spanish" in narrator.default_options["instructions"]
    assert "ONE number" in narrator.default_options["instructions"]


def test_model_options_carry_schema_and_limits():
    opts = model_options(Analysis, "gpt-5-mini")
    assert opts["response_format"] is Analysis
    assert opts["max_tokens"] == 2500
    assert opts["reasoning"] == {"effort": "minimal"}
    assert "reasoning" not in model_options(Analysis, "gpt-4.1-mini")


def test_settings_read_agent_mode_and_app_insights(monkeypatch):
    monkeypatch.setenv("BTS_AGENT_MODE", "simple")
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=abc")
    settings = Settings(_env_file=None)
    assert settings.agent_mode == "simple"
    assert settings.app_insights_connection_string == "InstrumentationKey=abc"


def test_settings_ignore_empty_env_values(monkeypatch):
    monkeypatch.setenv("BTS_AGENT_MODE", "")
    monkeypatch.setenv("BTS_FOUNDRY_ENDPOINT", "")
    settings = Settings(_env_file=None)
    assert settings.agent_mode is None and settings.foundry_endpoint is None
