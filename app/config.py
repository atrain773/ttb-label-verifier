"""Application settings, loaded from environment variables (and a local .env file).

Keeping every tunable here means deployment config (Render today, Azure later)
never requires a code change.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    extraction_model: str = "claude-opus-5-5"


@lru_cache
def get_settings() -> Settings:
    return Settings()
