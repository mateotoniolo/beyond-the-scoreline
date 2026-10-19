"""Microsoft Foundry client: structured JSON output through the OpenAI v1 endpoint.

Verified against the Microsoft Learn page "How to use structured outputs with Azure OpenAI in
Microsoft Foundry Models" (updated 2026-08-24): the plain ``OpenAI`` client pointed at
``https://<resource>.openai.azure.com/openai/v1/`` with an API key or an Entra token provider,
and ``responses.parse(..., text_format=PydanticModel)`` returning ``output_parsed``.
"""

from __future__ import annotations

import logging
from typing import TypeVar

from openai import APIError, AsyncOpenAI
from pydantic import BaseModel, ValidationError

from bts.config import Settings
from bts.insights.llm import FakeLLM, LLMClient, LLMError

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
ENTRA_SCOPE = "https://ai.azure.com/.default"


class FoundryClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.foundry_endpoint:
            raise ValueError("BTS_FOUNDRY_ENDPOINT is required")
        self.model = settings.foundry_model
        api_key: object = settings.foundry_api_key
        if not api_key:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            api_key = get_bearer_token_provider(DefaultAzureCredential(), ENTRA_SCOPE)
        self._client = AsyncOpenAI(
            base_url=settings.foundry_endpoint, api_key=api_key, max_retries=1
        )

    async def complete_json(
        self, *, system: str, user: str, schema: type[T], timeout_s: float = 20.0
    ) -> T:
        kwargs: dict = {}
        if self.model.startswith(("gpt-5", "o")):
            kwargs["reasoning"] = {"effort": "low"}
        try:
            response = await self._client.with_options(timeout=timeout_s).responses.parse(
                model=self.model,
                instructions=system,
                input=user,
                text_format=schema,
                max_output_tokens=800,
                **kwargs,
            )
        except APIError as exc:
            raise LLMError(f"{type(exc).__name__}: {exc}") from exc
        except ValidationError as exc:
            raise LLMError(f"response does not match {schema.__name__}: {exc}") from exc
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
