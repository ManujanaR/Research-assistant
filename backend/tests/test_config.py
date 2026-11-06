import os
from unittest.mock import patch

from app.core.config import Settings


def test_default_settings() -> None:
    """Verify that default settings match AGENTS.md requirements."""
    # Ensure environment variables don't pollute default test
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings()
        assert settings.llm_provider == "openai"
        assert settings.openai_api_key == ""
        assert settings.anthropic_api_key == ""
        assert settings.model_name == "gpt-4o"
        assert settings.max_upload_mb == 20
        assert settings.cors_origins == "http://localhost:3000"
        assert settings.cors_origins_list == ["http://localhost:3000"]


def test_custom_environment_overrides() -> None:
    """Verify that settings correctly load overrides from environment variables."""
    env_vars = {
        "LLM_PROVIDER": "anthropic",
        "OPENAI_API_KEY": "sk-mock-openai-key",
        "ANTHROPIC_API_KEY": "sk-mock-anthropic-key",
        "MODEL_NAME": "claude-sonnet-4-5",
        "MAX_UPLOAD_MB": "50",
        "CORS_ORIGINS": "http://localhost:3000, https://research.mitra.ai , http://127.0.0.1:3000",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        settings = Settings()
        assert settings.llm_provider == "anthropic"
        assert settings.openai_api_key == "sk-mock-openai-key"
        assert settings.anthropic_api_key == "sk-mock-anthropic-key"
        assert settings.model_name == "claude-sonnet-4-5"
        assert settings.max_upload_mb == 50
        assert settings.cors_origins_list == [
            "http://localhost:3000",
            "https://research.mitra.ai",
            "http://127.0.0.1:3000",
        ]


def test_cors_origins_list_empty_handling() -> None:
    """Verify handling of empty or whitespace-only CORS string."""
    with patch.dict(os.environ, {"CORS_ORIGINS": "  ,  "}, clear=True):
        settings = Settings()
        assert settings.cors_origins_list == []
