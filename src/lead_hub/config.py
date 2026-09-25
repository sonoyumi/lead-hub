"""Settings from environment variables / .env (pydantic-settings validates types and ranges)."""

from __future__ import annotations

from functools import cached_property
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/leads.db"

    # Keys: sites/forms send leads with an intake key; the management API needs the admin key.
    intake_keys: Annotated[list[SecretStr], NoDecode] = Field(default_factory=list)  # "key1,key2" in .env
    admin_key: SecretStr = SecretStr("")

    # Telegram notifications (optional: without them notifications are only logged)
    bot_token: SecretStr = SecretStr("")
    admin_chat_id: str = ""  # escalations and the daily digest

    timezone: str = "Europe/Rome"
    sla_minutes: int = Field(default=30, ge=1, le=24 * 60)  # a new lead must be taken within this time
    duplicate_window_hours: int = Field(default=24, ge=0, le=24 * 30)
    digest_hour: int = Field(default=19, ge=0, le=23)  # local time of the daily digest

    # Websites allowed to send leads straight from the browser (JavaScript forms). Empty = server-to-server only.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @field_validator("intake_keys", "cors_origins", mode="before")
    @classmethod
    def _split_keys(cls, value):
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        ZoneInfo(value)  # raises for unknown names
        return value

    @cached_property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.bot_token.get_secret_value())
