from pathlib import Path
from typing import Literal
from pydantic import Field

from pydantic_settings import BaseSettings, SettingsConfigDict


# Local development keeps .env beside docker-compose.yml, outside the API package.
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Server-side runtime configuration."""

    ai_provider: Literal["gemini", "openai"] = "gemini"
    allow_provider_fallback: bool = False
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_timeout_ms: int = 30_000
    gemini_max_retries: int = 3
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_timeout_ms: int = 30_000
    openai_max_retries: int = 3
    api_rate_limit_requests: int = Field(default=120, ge=10, le=10_000)
    api_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3_600)
    frontend_origin: str = "http://localhost:3000"
    interview_question_limit: int = Field(default=12, ge=1, le=100)
    database_url: str = (
        "postgresql+psycopg://interview_graph:change_me@localhost:5432/interview_graph"
    )
    postgres_db: str | None = None
    postgres_user: str | None = None
    postgres_password: str | None = None

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")


settings = Settings()
