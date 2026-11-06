from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: Literal["openai"] = Field(
        default="openai",
        alias="LLM_PROVIDER",
    )
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    model_name: str = Field(default="gpt-4o", alias="MODEL_NAME")
    max_upload_mb: int = Field(default=20, gt=0, alias="MAX_UPLOAD_MB")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS_ORIGINS string into a list of trimmed URLs."""
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()
