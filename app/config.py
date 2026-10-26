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
    # Hard ceiling per single-label attempt. The slowest measured read was 4.6s; an agent
    # should get an answer or a "try again" message quickly, not wait half a minute.
    extraction_timeout_seconds: float = 8.0
    # Batch rows can wait longer, since no one is watching a single row.
    batch_timeout_seconds: float = 20.0
    # Labels checked at once in a batch. Bounded by the API account's rate limit.
    batch_concurrency: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
