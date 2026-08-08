from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None
    telegram_owner_user_id: int | None = None

    request_timeout_seconds: float = 20.0
    user_agent: str = "EventRadar/0.1"

    weather_location_name: str = "Santa Rosa, CA"
    weather_latitude: float = Field(default=38.44047, ge=-90, le=90)
    weather_longitude: float = Field(default=-122.71443, ge=-180, le=180)
    weather_timezone: str = "America/Los_Angeles"

    hike_catalog_path: Path = Path("data/hikes.json")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
