"""Microsoft Foundry client: structured JSON output through the OpenAI v1 endpoint.

Verified against the Microsoft Learn page "How to use structured outputs with Azure OpenAI in
Microsoft Foundry Models" (updated 2026-08-24): the plain ``OpenAI`` client pointed at
``https://<resource>.openai.azure.com/openai/v1/`` with an API key or an Entra token provider,
and ``responses.parse(..., text_format=PydanticModel)`` returning ``output_parsed``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from openai import APIError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from bts.config import Settings
from bts.insights.llm import FakeLLM, LLMClient, LLMError

if TYPE_CHECKING:
    from bts.insights.crew.crew import AgentCrew

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
CrewFactory = Callable[[], "AgentCrew"]
ENTRA_SCOPE = "https://ai.azure.com/.default"
# Reasoning tokens are billed inside max_output_tokens on gpt-5 models: an 800-token cap
# truncated most JSON replies in testing, so the cap is generous and reasoning is minimal.
MAX_OUTPUT_TOKENS = 2500
REASONING_EFFORT = "minimal"


class FoundryClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.foundry_endpoint:
            raise ValueError("BTS_FOUNDRY_ENDPOINT is required")
        self.model = settings.foundry_model
        api_key: object = settings.foundry_api_key
        if not api_key:
            from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider

            api_key = get_bearer_token_provider(DefaultAzureCredential(), ENTRA_SCOPE)
        self._client = AsyncOpenAI(
            base_url=settings.foundry_endpoint, api_key=api_key, max_retries=1
        )

    async def complete_json(
        self, *, system: str, user: str, schema: type[T], timeout_s: float = 20.0
    ) -> T:
        kwargs: dict = {}
        if self.model.startswith(("gpt-5", "o")):
            # Reasoning tokens count against max_output_tokens; keep them minimal for latency.
            kwargs["reasoning"] = {"effort": REASONING_EFFORT}
        try:
            response = await self._client.with_options(timeout=timeout_s).responses.parse(
                model=self.model,
                instructions=system,
                input=user,
                text_format=schema,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                **kwargs,
            )
        except APIError as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
        except ValidationError as exc:
            raise LLMError(f"response does not match {schema.__name__}: {exc}") from exc
        status = getattr(response, "status", None)
        if status == "incomplete":
            details = getattr(response, "incomplete_details", None)
            reason = getattr(details, "reason", "unknown")
            raise LLMError(f"incomplete response for {schema.__name__}: {reason}")
        parsed = response.output_parsed
        if parsed is None:
            raise LLMError(f"empty or refused response for {schema.__name__}")
        return parsed


def make_llm(settings: Settings) -> LLMClient:
    """Foundry when an endpoint is configured, otherwise a fake that always falls back."""
    if settings.foundry_endpoint:
        log.info("LLM: Microsoft Foundry model %s", settings.foundry_model)
        return FoundryClient(settings)
    log.warning("LLM: no BTS_FOUNDRY_ENDPOINT set; insights will use templates only")
    return FakeLLM([])


def make_crew(settings: Settings) -> CrewFactory | None:
    """A per-session crew factory sharing one chat client, or None for the simple pipeline.

    ``BTS_AGENT_MODE`` decides; unset, the crew is on whenever a model endpoint exists.
    """
    mode = settings.agent_mode or ("crew" if settings.foundry_endpoint else "simple")
    if mode != "crew":
        log.info("agents: simple pipeline (BTS_AGENT_MODE=%s)", mode)
        return None
    if not settings.foundry_endpoint or not settings.foundry_api_key:
        log.warning("agents: the crew needs BTS_FOUNDRY_ENDPOINT and an API key; simple pipeline")
        return None
    from bts.insights.crew.agents import make_chat_client
    from bts.insights.crew.crew import AgentCrew

    client = make_chat_client(settings)
    model = settings.foundry_model
    log.info("agents: Microsoft Agent Framework crew on %s", model)
    return lambda: AgentCrew(client, model)
