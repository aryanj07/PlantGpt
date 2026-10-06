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
    # RAG embeddings run locally via fastembed (Hugging Face model, no API
    # key) - unrelated to openai_api_key above, which is only for chat.
    embedding_model: str = "BAAI/bge-small-en-v1.5"

    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"
    openrouter_site_url: str = ""
    openrouter_site_name: str = ""

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-flash"

    anthropic_api_key: str = ""

    # Phase 4 MCP tool broker: web search/scrape (tavily.com, permanent free
    # tier, no card). Live sensor data is a self-hosted simulator - needs no key.
    tavily_api_key: str = ""

    # Flat per-tenant budget (plan Section G.1 quota_ledger, Q). One value
    # for every tenant since there's no plan/tier data yet - real per-plan
    # budgets are a later task once tenants/subscriptions exist.
    default_monthly_budget_usd: float = 1.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
