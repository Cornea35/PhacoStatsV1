"""Application settings for PhacoStats."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "PhacoStats V1"
    organization_name: str = "CODET Vision Institute"
    database_url: str = f"sqlite:///{BASE_DIR / 'phacostats.db'}"
    secret_key: str = "dev-secret-change-me"
    debug: bool = False
    session_cookie_name: str = "phacostats_session"
    session_max_age_seconds: int = 60 * 60 * 12  # 12 hours


@lru_cache
def get_settings() -> Settings:
    return Settings()
