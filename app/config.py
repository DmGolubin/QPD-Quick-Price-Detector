"""Application configuration via Pydantic Settings."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    POLL_INTERVAL: int = 300
    PORT: int = 8000
    API_SECRET_KEY: str = "change-me-in-production"
    PROXY_URL: Optional[str] = None
    CORS_ORIGINS: str = "*"
    MAX_BROWSERS: int = 3
    MAX_CONCURRENT_CHECKS: int = 5
    LOG_LEVEL: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()  # type: ignore[call-arg]
