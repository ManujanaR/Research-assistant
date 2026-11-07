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
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", alias="OPENAI_BASE_URL"
    )
    model_name: str = Field(default="gpt-4o", alias="MODEL_NAME")
    embedding_model: str = Field(
        default="text-embedding-3-small", alias="EMBEDDING_MODEL"
    )
    max_upload_mb: int = Field(default=20, gt=0, alias="MAX_UPLOAD_MB")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")
    summary_cache_dir: str = Field(
        default=".cache/summaries", alias="SUMMARY_CACHE_DIR"
    )
    chroma_dir: str = Field(default=".chroma", alias="CHROMA_DIR")

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
