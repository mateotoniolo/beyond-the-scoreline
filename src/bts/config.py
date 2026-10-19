"""Application settings loaded from environment variables (prefix ``BTS_``)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BTS_", env_file=".env", extra="ignore")

    foundry_endpoint: str | None = None
    foundry_api_key: str | None = None
    foundry_model: str = "gpt-5-mini"
    cosmos_endpoint: str | None = None
    cosmos_key: str | None = None
    cosmos_database: str = "bts"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
