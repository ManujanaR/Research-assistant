from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.cache import SummaryCache
from app.services.summary_service import InMemoryPaperTextStore, PaperTextStore

_paper_text_store = InMemoryPaperTextStore()


def get_summary_cache() -> SummaryCache:
    """Build and return a SummaryCache using the configured summary_cache_dir."""
    settings = get_settings()
    return SummaryCache(cache_dir=Path(settings.summary_cache_dir))


def get_paper_text_store() -> PaperTextStore:
    """Return the process-wide in-memory PaperTextStore singleton."""
    return _paper_text_store


def get_llm_client() -> Any:
    """Build the OpenAI async client from OPENAI_API_KEY only when called."""
    settings = get_settings()
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=settings.openai_api_key)
