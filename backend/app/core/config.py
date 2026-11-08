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


def _resolve_database_url(url: str) -> str:
    sqlite_prefix = "sqlite:///"
    if url.startswith(sqlite_prefix):
        raw_path = url[len(sqlite_prefix) :]
        if raw_path != ":memory:" and not raw_path.startswith("/"):
            resolved = _resolve_backend_path(raw_path)
            return f"sqlite:///{resolved}"
    return url


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
    rewrite_model: str = Field(default="gpt-4o-mini", alias="REWRITE_MODEL")
    rewrite_history_turns: int = Field(default=3, alias="REWRITE_HISTORY_TURNS")
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

    environment: str = Field(default="development", alias="ENVIRONMENT")
    auth_secret_key: str = Field(default="", alias="AUTH_SECRET_KEY")
    auth_token_ttl_minutes: int = Field(
        default=60, gt=0, alias="AUTH_TOKEN_TTL_MINUTES"
    )
    database_url: str = Field(default="sqlite:///./data/app.db", alias="DATABASE_URL")

    def model_post_init(self, context: Any, /) -> None:
        """Resolve directory paths relative to the backend folder and validate settings."""
        self.summary_cache_dir = _resolve_backend_path(self.summary_cache_dir)
        self.chroma_dir = _resolve_backend_path(self.chroma_dir)
        self.database_url = _resolve_database_url(self.database_url)
        logger.info("Resolved SUMMARY_CACHE_DIR: %s", self.summary_cache_dir)
        logger.info("Resolved CHROMA_DIR: %s", self.chroma_dir)
        logger.info("Resolved DATABASE_URL: %s", self.database_url)

        if (
            self.environment.strip().lower() == "production"
            and not self.auth_secret_key.strip()
        ):
            raise ValueError("AUTH_SECRET_KEY is required in production environment")

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS_ORIGINS string into a list of trimmed URLs."""
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]

    @property
    def REWRITE_MODEL(self) -> str:
        return self.rewrite_model

    @property
    def REWRITE_HISTORY_TURNS(self) -> int:
        return self.rewrite_history_turns


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()
