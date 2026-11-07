import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _resolve_backend_path(raw_path: str) -> str:
    path = Path(raw_path)
    if not path.is_absolute():
        return str((BACKEND_DIR / path).resolve())
    return str(path.resolve())


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
    citation_max_distance: float = Field(
        default=0.6, gt=0.0, alias="CITATION_MAX_DISTANCE"
    )
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")
    summary_cache_dir: str = Field(
        default=".cache/summaries", alias="SUMMARY_CACHE_DIR"
    )
    chroma_dir: str = Field(default=".chroma", alias="CHROMA_DIR")

    def model_post_init(self, context: Any, /) -> None:
        """Resolve directory paths relative to the backend folder and log them."""
        self.summary_cache_dir = _resolve_backend_path(self.summary_cache_dir)
        self.chroma_dir = _resolve_backend_path(self.chroma_dir)
        logger.info("Resolved SUMMARY_CACHE_DIR: %s", self.summary_cache_dir)
        logger.info("Resolved CHROMA_DIR: %s", self.chroma_dir)

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
