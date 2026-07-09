from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "trading-platform"
    debug: bool = False

    # Supabase — Postgres connection string from the dashboard
    # (Settings → Database → Connection string → URI, "Transaction" pooler
    # on port 6543 for serverless, "Session" pooler / direct for workers).
    database_url: str = "postgresql+asyncpg://postgres:postgres@127.0.0.1:54322/postgres"

    # Supabase project (Settings → API)
    supabase_url: str = ""
    supabase_service_role_key: str = ""  # server-only; bypasses RLS
    supabase_jwt_secret: str = ""        # verifies user JWTs on API requests

    # Broker APIs (Phase 1)
    angelone_api_key: str = ""
    angelone_client_id: str = ""
    dhan_client_id: str = ""
    dhan_access_token: str = ""

    # Alerts
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Inbound webhooks (TradingView Pro alerts). Any long random string.
    webhook_secret: str = ""

    # AI (LiteLLM reads provider keys from the environment)
    ai_monthly_budget_usd: float = 20.0

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
