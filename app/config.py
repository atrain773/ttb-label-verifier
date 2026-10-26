"""Application settings, loaded from environment variables (and a local .env file).

Keeping every tunable here means deployment config (Render today, Azure later)
never requires a code change.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Real environment variables (e.g. on Render) take precedence over the local .env file.
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    anthropic_api_key: str = ""
    extraction_model: str = "claude-sonnet-5-5"  # chosen from docs/eval_results.md
    # Lower effort = less model thinking = faster responses. Label transcription is a simple task.
    extraction_effort: str = "low"
    # Hard ceiling per label; the target is ~5 seconds.
    extraction_timeout_seconds: float = 20.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
