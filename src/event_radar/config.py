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
    user_context_path: Path = Path("config/user_context.json")
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-5.6"
    openai_event_analysis_model: str | None = None
    openai_web_discovery_model: str | None = None
    openai_curation_model: str | None = None
    openai_timeout_seconds: float = Field(default=120.0, gt=0)
    event_analysis_prompt_path: Path = Path("prompts/event_analysis.md")
    web_discovery_prompt_path: Path = Path("prompts/web_event_discovery.md")
    curation_prompt_path: Path = Path("prompts/weekend_curation.md")
    curation_output_dir: Path = Path("output")

    @property
    def resolved_event_analysis_model(self) -> str:
        return self.openai_event_analysis_model or self.openai_model

    @property
    def resolved_web_discovery_model(self) -> str:
        return self.openai_web_discovery_model or self.openai_model

    @property
    def resolved_curation_model(self) -> str:
        return self.openai_curation_model or self.openai_model

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
