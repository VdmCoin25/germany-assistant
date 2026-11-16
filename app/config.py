"""Application settings. All values come from environment variables / .env."""
from functools import lru_cache
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore",
                                      populate_by_name=True)

    # Telegram
    bot_token: str
    bot_name: str = "Germany Assistant"
    admin_ids: Annotated[list[int], NoDecode] = []
    # Webhook mode: Telegram pushes updates to WEBAPP_URL/tg/webhook. Needed on hosts that
    # sleep when idle (e.g. Render free tier). False = long polling.
    webhook_mode: bool = False
    webhook_secret: str | None = None

    # Optional HTTP(S) proxy for Telegram API calls, e.g. http://user:pass@host:3128
    telegram_proxy: str | None = None

    # Languages offered in the bot. Add "de" here after creating app/i18n/locales/de.json
    languages: Annotated[list[str], NoDecode] = ["uk", "ru"]
    default_language: str = "uk"

    # Storage
    database_url: str = "sqlite+aiosqlite:///./data/bot.db"
    redis_url: str | None = None

    # Mini App (must be a public HTTPS URL for Telegram to open it)
    # On Render, RENDER_EXTERNAL_URL and PORT are provided automatically.
    webapp_url: str | None = Field(default=None, validation_alias=AliasChoices("WEBAPP_URL", "RENDER_EXTERNAL_URL"))
    run_webapp: bool = True
    webapp_host: str = "0.0.0.0"
    webapp_port: int = Field(default=8080, validation_alias=AliasChoices("WEBAPP_PORT", "PORT"))
    webapp_init_data_ttl: int = 86400  # seconds

    # Limits / safety
    rate_limit_per_minute: int = 20
    max_file_size_mb: int = 10

    # Job exchange
    employer_pilot_days: int = 30
    employer_price_eur: int = 100
    vacancy_days: int = 30

    # Analytics: salt for pseudonymous user hash (keep secret, change before production)
    analytics_salt: str = "change-me"

    # AI provider (stage B). "none" = not connected, bot says so honestly.
    ai_provider: str = "none"
    ai_api_key: str | None = None
    ai_model: str | None = None

    log_level: str = "INFO"

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_ids(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.replace(" ", "").split(",") if x]
        return v

    @field_validator("languages", mode="before")
    @classmethod
    def _parse_langs(cls, v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, v: str) -> str:
        # Hosting providers give postgres:// or postgresql:// — SQLAlchemy async needs +asyncpg
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+asyncpg://" + v[len(prefix):]
        return v

    @field_validator("webapp_url")
    @classmethod
    def _https_only(cls, v):
        if v and not v.startswith("https://"):
            raise ValueError("WEBAPP_URL must start with https:// (Telegram requirement)")
        return v.rstrip("/") if v else None


    @property
    def webhook_token(self) -> str | None:
        """Telegram allows only [A-Za-z0-9_-] in secret_token, so use a hex digest of the secret."""
        if not self.webhook_secret:
            return None
        import hashlib

        return hashlib.sha256(self.webhook_secret.encode()).hexdigest()


@lru_cache
def get_settings() -> Settings:
    return Settings()
