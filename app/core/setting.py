"""Configuration definition."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "settings"]

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class EnvSettingsOptions(Enum):
    production = "production"
    staging = "staging"
    development = "dev"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=False, extra="ignore"
    )

    # Project Configuration
    ENV_SETTING: EnvSettingsOptions = Field(
        "production", examples=["production", "staging", "dev"]
    )
    # Example "postgresql+psycopg://username:password@localhost:5432/db_name"
    PG_DSN: str = Field()


settings = Settings()
