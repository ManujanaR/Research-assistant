from pathlib import Path
from typing import Annotated, Any

import chromadb
from chromadb.api import ClientAPI
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.user import User
from app.services.cache import SummaryCache
from app.services.qa import EmbedFn
from app.services.summary_service import InMemoryPaperTextStore, PaperTextStore
from app.services.token_service import decode_access_token

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


def create_async_openai_client() -> Any:
    """Build an AsyncOpenAI client configured with openai_api_key and openai_base_url."""
    settings = get_settings()
    from openai import AsyncOpenAI

    api_key = settings.openai_api_key or "sk-mock-key-for-test-injection"
    return AsyncOpenAI(
        api_key=api_key,
        base_url=settings.openai_base_url,
    )


def get_embedding_function() -> EmbedFn:
    """Return the OpenAI async embedding function using configured embedding_model."""
    settings = get_settings()

    async def _embed(texts: list[str]) -> list[list[float]]:
        client = create_async_openai_client()
        response = await client.embeddings.create(
            model=settings.embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    return _embed


def get_llm_client() -> Any:
    """Build the OpenAI async client from OPENAI_API_KEY only when called."""
    return create_async_openai_client()


def get_chat_llm_client() -> Any:
    """Build the OpenAI async client for chat from OPENAI_API_KEY only when called."""
    return create_async_openai_client()


async def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Read auth_token from cookie, verify JWT, load user, and verify token version against DB."""
    token = request.cookies.get("auth_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        )

    user_id = payload.get("sub")
    if not user_id or not isinstance(user_id, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    token_version = payload.get("token_version")
    if token_version is None:
        token_version = payload.get("v")

    if token_version is None or token_version != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has ended. Sign in again to continue.",
        )

    return user
