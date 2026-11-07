import os
from unittest.mock import patch

import pydantic
import pytest

from app.core.config import Settings


def test_default_settings() -> None:
    """Verify that default settings match AGENTS.md requirements."""
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=None)
        assert settings.llm_provider == "openai"
        assert settings.openai_api_key == ""
        assert settings.openai_base_url == "https://api.openai.com/v1"
        assert settings.model_name == "gpt-4o"
        assert settings.embedding_model == "text-embedding-3-small"
        assert settings.max_upload_mb == 20
        assert settings.cors_origins == "http://localhost:3000"
        assert settings.cors_origins_list == ["http://localhost:3000"]


def test_custom_environment_overrides() -> None:
    """Verify that settings correctly load overrides from environment variables."""
    env_vars = {
        "LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "sk-mock-openai-key",
        "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
        "MODEL_NAME": "gpt-4o-mini",
        "EMBEDDING_MODEL": "openai/text-embedding-3-small",
        "MAX_UPLOAD_MB": "50",
        "CORS_ORIGINS": "http://localhost:3000, https://research.mitra.ai , http://127.0.0.1:3000",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        settings = Settings(_env_file=None)
        assert settings.llm_provider == "openai"
        assert settings.openai_api_key == "sk-mock-openai-key"
        assert settings.openai_base_url == "https://openrouter.ai/api/v1"
        assert settings.model_name == "gpt-4o-mini"
        assert settings.embedding_model == "openai/text-embedding-3-small"
        assert settings.max_upload_mb == 50
        assert settings.cors_origins_list == [
            "http://localhost:3000",
            "https://research.mitra.ai",
            "http://127.0.0.1:3000",
        ]


def test_cors_origins_list_empty_handling() -> None:
    """Verify handling of empty or whitespace-only CORS string."""
    with patch.dict(os.environ, {"CORS_ORIGINS": "  ,  "}, clear=True):
        settings = Settings(_env_file=None)
        assert settings.cors_origins_list == []


@pytest.mark.parametrize("invalid_mb", ["0", "-5"])
def test_invalid_max_upload_mb_raises_validation_error(invalid_mb: str) -> None:
    """Verify that MAX_UPLOAD_MB <= 0 raises pydantic.ValidationError."""
    with (
        patch.dict(os.environ, {"MAX_UPLOAD_MB": invalid_mb}, clear=True),
        pytest.raises(pydantic.ValidationError),
    ):
        Settings(_env_file=None)
