import logging
from typing import Annotated, Any

import openai
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import (
    get_current_user,
    get_llm_client,
    get_paper_text_store,
    get_summary_cache,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.summary import SummaryRequest, SummarySchema
from app.services.cache import SummaryCache
from app.services.ownership_service import is_owner
from app.services.summarizer import (
    SUMMARY_GENERATION_FAILED_MESSAGE,
    SummaryGenerationError,
    generate_summary,
)
from app.services.summary_service import PaperTextStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["summary"])


@router.post("/summary", response_model=SummarySchema)
async def get_or_generate_summary(
    request: SummaryRequest,
    raw_request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    cache: Annotated[SummaryCache, Depends(get_summary_cache)],
    text_store: Annotated[PaperTextStore, Depends(get_paper_text_store)],
) -> SummarySchema:
    """Retrieve cached summary or generate a new structured summary from stored paper text."""
    doc_hash = request.doc_hash

    # Step 1: Ownership check runs first, before cache, text, or index access
    if not is_owner(doc_hash, current_user.id, db=db):
        raise HTTPException(
            status_code=404,
            detail="Document not found. Upload the PDF first.",
        )

    # Step 2: Cache check (hit returns immediately without touching LLM client)
    cached = cache.get(doc_hash)
    if cached is not None:
        return SummarySchema.model_validate(cached)

    # Step 3: Check OpenAI API key on cache miss
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="OpenAI API key is not configured.",
        )

    # Step 4: Check if document text exists in store
    text = text_store.get_text(doc_hash)
    if text is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found. Upload the PDF first.",
        )

    # Step 5: Resolve LLM client (respecting app.dependency_overrides) and generate summary
    client_getter = raw_request.app.dependency_overrides.get(
        get_llm_client, get_llm_client
    )
    client: Any = client_getter()

    try:
        summary = await generate_summary(text, client)
    except openai.AuthenticationError as exc:
        logger.warning(
            "AI provider AuthenticationError during summary: status %s",
            getattr(exc, "status_code", 401),
        )
        raise HTTPException(
            status_code=503,
            detail="AI provider authentication failed.",
        ) from exc
    except openai.RateLimitError as exc:
        logger.warning(
            "AI provider RateLimitError during summary: status %s",
            getattr(exc, "status_code", 429),
        )
        raise HTTPException(
            status_code=503,
            detail="AI provider rate limit exceeded.",
        ) from exc
    except (openai.APIConnectionError, openai.APITimeoutError) as exc:
        logger.warning(
            "AI provider connection/timeout error during summary: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="AI provider connection or timeout error.",
        ) from exc
    except openai.APIStatusError as exc:
        logger.warning(
            "AI provider APIStatusError during summary: status %s",
            exc.status_code,
        )
        raise HTTPException(
            status_code=502,
            detail=f"The AI provider returned an error (status {exc.status_code}). Check MODEL_NAME and EMBEDDING_MODEL in backend/.env.",
        ) from exc
    except SummaryGenerationError as exc:
        raise HTTPException(
            status_code=502,
            detail=SUMMARY_GENERATION_FAILED_MESSAGE,
        ) from exc

    # Step 6: Store in cache and return
    cache.set(doc_hash, summary.model_dump())
    return summary
