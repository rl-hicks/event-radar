from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_OPENAI_MODEL = "gpt-5.6"
DEFAULT_WEB_DISCOVERY_MODEL = "gpt-6.1-sol"


class ModelPricingRates(BaseModel):
    input_usd_per_million: float = Field(ge=0)
    cached_input_usd_per_million: float | None = Field(default=None, ge=0)
    output_usd_per_million: float = Field(ge=0)


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
    personal_experience_context_path: Path = Path(
        "config/personal_experience_preference_context.md"
    )
    openai_api_key: SecretStr | None = None
    openai_model: str = DEFAULT_OPENAI_MODEL
    openai_model_pricing: dict[str, ModelPricingRates] = Field(
        default_factory=lambda: {
            DEFAULT_OPENAI_MODEL: ModelPricingRates(
                input_usd_per_million=4.00,
                cached_input_usd_per_million=0.40,
                output_usd_per_million=20.00,
            ),
            DEFAULT_WEB_DISCOVERY_MODEL: ModelPricingRates(
                input_usd_per_million=2.00,
                cached_input_usd_per_million=0.10,
                output_usd_per_million=10.00,
            ),
        }
    )
    openai_event_analysis_model: str | None = None
    openai_web_discovery_model: str | None = DEFAULT_WEB_DISCOVERY_MODEL
    openai_curation_model: str | None = None
    openai_timeout_seconds: float = Field(default=120.0, gt=0)
    event_analysis_prompt_path: Path = Path("prompts/event_analysis.md")
    web_discovery_prompt_path: Path = Path("prompts/web_event_discovery.md")
    curation_prompt_path: Path = Path("prompts/weekend_curation.md")
    curation_output_dir: Path = Path("output")

    # E0 public-product foundation. These are optional at import time so the
    # existing personal CLI remains usable without web/API configuration.
    database_url: SecretStr | None = None
    web_origins: str = "http://localhost:5173"
    supabase_url: str | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_jwt_secret: SecretStr | None = None

    @property
    def resolved_event_analysis_model(self) -> str:
        return self.openai_event_analysis_model or self.openai_model

    @property
    def resolved_web_discovery_model(self) -> str:
        return self.openai_web_discovery_model or self.openai_model

    @property
    def resolved_curation_model(self) -> str:
        return self.openai_curation_model or self.openai_model

    @property
    def web_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.web_origins.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
