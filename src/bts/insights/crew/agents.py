"""Agent factories: the model-backed roles sharing one Foundry chat client."""

from __future__ import annotations

from agent_framework import Agent
from agent_framework.openai import OpenAIChatClient, OpenAIChatOptions
from pydantic import BaseModel

from bts.config import Settings
from bts.insights.crew import prompts
from bts.insights.crew.context import MatchContext
from bts.insights.explainer import RecapOutput
from bts.insights.foundry import MAX_OUTPUT_TOKENS, REASONING_EFFORT
from bts.insights.schemas import Evidence, Lang, Profile
from bts.insights.verifier import ExplainerOutput, VerifierOutput

ANALYST = "tactical_analyst"
NARRATOR = "narrator"
FACT_CHECKER = "fact_checker"
PRODUCER = "producer"
CHECKER_TOOLS = frozenset({"get_team_stats", "get_player_stats", "get_momentum", "check_numbers"})
# Every model request (including each tool round) is bounded; the SDK default is 600 s.
REQUEST_TIMEOUT_S = 20.0


class Analysis(BaseModel):
    """What the tactical analyst hands to the narrator."""

    pattern: str
    key_numbers: list[Evidence]
    confidence: float


def resource_endpoint(foundry_endpoint: str) -> str:
    """``https://x.openai.azure.com/openai/v1/`` becomes ``https://x.openai.azure.com``."""
    return foundry_endpoint.split("/openai/")[0].rstrip("/")


def make_chat_client(settings: Settings) -> OpenAIChatClient:
    if not settings.foundry_endpoint or not settings.foundry_api_key:
        raise ValueError("BTS_FOUNDRY_ENDPOINT and BTS_FOUNDRY_API_KEY are required for the crew")
    client = OpenAIChatClient(
        model=settings.foundry_model,
        api_key=settings.foundry_api_key,
        azure_endpoint=resource_endpoint(settings.foundry_endpoint),
    )
    client.client = client.client.with_options(timeout=REQUEST_TIMEOUT_S, max_retries=1)
    return client


def model_options(response_format: type[BaseModel] | None, model: str) -> OpenAIChatOptions:
    """Per-run options: structured output, a generous token cap and minimal reasoning."""
    opts: OpenAIChatOptions = {"max_tokens": MAX_OUTPUT_TOKENS}
    if response_format is not None:
        opts["response_format"] = response_format
    if model.startswith(("gpt-5", "o")):
        opts["reasoning"] = {"effort": REASONING_EFFORT}
    return opts


def make_analyst(client: OpenAIChatClient, ctx: MatchContext) -> Agent:
    tools = [t for t in ctx.tools() if t.name != "check_numbers"]
    return Agent(
        client=client,
        name=ANALYST,
        instructions=prompts.analyst_instructions(),
        tools=tools,
        default_options=model_options(Analysis, client.model),
    )


def make_narrator(client: OpenAIChatClient, profile: Profile, lang: Lang) -> Agent:
    return Agent(
        client=client,
        name=NARRATOR,
        instructions=prompts.narrator_instructions(profile, lang),
        tools=[],
        default_options=model_options(ExplainerOutput, client.model),
    )


def make_fact_checker(client: OpenAIChatClient, ctx: MatchContext) -> Agent:
    tools = [t for t in ctx.tools() if t.name in CHECKER_TOOLS]
    return Agent(
        client=client,
        name=FACT_CHECKER,
        instructions=prompts.fact_checker_instructions(),
        tools=tools,
        default_options=model_options(VerifierOutput, client.model),
    )


def make_recap_narrator(client: OpenAIChatClient, profile: Profile, lang: Lang) -> Agent:
    return Agent(
        client=client,
        name=NARRATOR,
        instructions=prompts.recap_instructions(profile, lang),
        tools=[],
        default_options=model_options(RecapOutput, client.model),
    )
