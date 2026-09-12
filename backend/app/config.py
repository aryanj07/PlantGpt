from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Env-driven config. Every field has a safe local-dev default so the
    skeleton runs with zero external services (see backend/README.md).
    Real values for staging/prod come from the deploy platform's secret
    manager, never from a committed file (plan Section J.3)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    dev_mode: bool = True

    database_url: str = "sqlite:///./dev.db"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-only-placeholder-change-me"
    jwt_issuer: str = "plantgpt-backend"
    jwt_ttl_minutes: int = 30

    auth0_domain: str = ""
    auth0_audience: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-5"

    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_site_url: str = ""
    openrouter_site_name: str = ""

    anthropic_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
