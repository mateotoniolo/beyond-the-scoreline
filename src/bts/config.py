"""Application settings loaded from environment variables (prefix ``BTS_``)."""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

AgentMode = Literal["crew", "simple"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="BTS_",
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
        env_ignore_empty=True,  # the deploy script passes unset variables as ""
    )

    foundry_endpoint: str | None = None
    foundry_api_key: str | None = None
    foundry_model: str = "gpt-5-mini"
    # crew = Agent Framework roles (default when a model endpoint is set); simple = two prompts.
    agent_mode: AgentMode | None = None
    # Ask the match (question desk); unset = on whenever the crew is on.
    qa_enabled: bool | None = None
    # Azure AI Speech (narration); unset BTS_SPEECH_ENABLED = on whenever key and region are set.
    speech_key: str | None = None
    speech_region: str | None = None
    speech_enabled: bool | None = None
    cosmos_endpoint: str | None = None
    cosmos_key: str | None = None
    cosmos_database: str = "bts"
    # Azure's own variable name, so the Container App and the SDKs agree on it.
    app_insights_connection_string: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "APPLICATIONINSIGHTS_CONNECTION_STRING", "BTS_APP_INSIGHTS_CONNECTION_STRING"
        ),
    )
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
