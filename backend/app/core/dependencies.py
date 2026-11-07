from pathlib import Path
from typing import Annotated, Any

import chromadb
from chromadb.api import ClientAPI
from fastapi import Depends

from app.core.config import get_settings
from app.services.cache import SummaryCache
from app.services.qa import EmbedFn
from app.services.summary_service import InMemoryPaperTextStore, PaperTextStore

# Process-wide shared singleton for paper text store
_paper_text_store = InMemoryPaperTextStore()


def get_summary_cache() -> SummaryCache:
    """Build and return a SummaryCache using the configured summary_cache_dir."""
    settings = get_settings()
    return SummaryCache(cache_dir=Path(settings.summary_cache_dir))


def get_chroma_client() -> ClientAPI:
    """Return a ChromaDB persistent client pointing to settings.chroma_dir."""
    settings = get_settings()
    return chromadb.PersistentClient(path=settings.chroma_dir)


def get_paper_text_store(
    chroma_client: Annotated[ClientAPI | None, Depends(get_chroma_client)] = None,
) -> PaperTextStore:
    """Return the process-wide in-memory PaperTextStore singleton with Chroma fallback."""
    if chroma_client is not None:
        _paper_text_store.chroma_client = chroma_client
    elif _paper_text_store.chroma_client is None:
        _paper_text_store.chroma_client = get_chroma_client()
    return _paper_text_store


def get_embedding_function() -> EmbedFn:
    """Return the OpenAI async embedding function using text-embedding-3-small."""
    settings = get_settings()

    async def _embed(texts: list[str]) -> list[list[float]]:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        return [item.embedding for item in response.data]

    return _embed


def get_llm_client() -> Any:
    """Build the OpenAI async client from OPENAI_API_KEY only when called."""
    settings = get_settings()
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=settings.openai_api_key)


def get_chat_llm_client() -> Any:
    """Build the OpenAI async client for chat from OPENAI_API_KEY only when called."""
    return get_llm_client()
