import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import dependencies
from app.core.config import Settings


def test_default_provider_settings() -> None:
    """Default settings have OPENAI_BASE_URL and EMBEDDING_MODEL set to OpenAI defaults."""
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=None)
        assert settings.openai_base_url == "https://api.openai.com/v1"
        assert settings.embedding_model == "text-embedding-3-small"


def test_custom_openai_base_url_propagates_to_client() -> None:
    """Setting OPENAI_BASE_URL propagates to AsyncOpenAI client construction."""
    custom_settings = Settings(
        OPENAI_API_KEY="test-openrouter-key",
        OPENAI_BASE_URL="https://openrouter.ai/api/v1",
        _env_file=None,
    )
    with (
        patch("app.core.dependencies.get_settings", return_value=custom_settings),
        patch("openai.AsyncOpenAI") as mock_openai,
    ):
        dependencies.create_async_openai_client()
        mock_openai.assert_called_once_with(
            api_key="test-openrouter-key",
            base_url="https://openrouter.ai/api/v1",
        )


@pytest.mark.asyncio
async def test_custom_embedding_model_propagates_to_embedding_call() -> None:
    """Setting EMBEDDING_MODEL propagates to client.embeddings.create."""
    custom_settings = Settings(
        OPENAI_API_KEY="test-key",
        EMBEDDING_MODEL="openai/text-embedding-3-small",
        _env_file=None,
    )
    fake_item = MagicMock()
    fake_item.embedding = [0.1, 0.2, 0.3]
    fake_response = MagicMock(data=[fake_item])

    mock_client = MagicMock()
    mock_client.embeddings.create = AsyncMock(return_value=fake_response)

    with (
        patch("app.core.dependencies.get_settings", return_value=custom_settings),
        patch(
            "app.core.dependencies.create_async_openai_client",
            return_value=mock_client,
        ),
    ):
        embed_fn = dependencies.get_embedding_function()
        result = await embed_fn(["sample paper text"])

        assert result == [[0.1, 0.2, 0.3]]
        mock_client.embeddings.create.assert_awaited_once_with(
            model="openai/text-embedding-3-small",
            input=["sample paper text"],
        )
