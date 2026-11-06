from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import get_settings
from app.core.dependencies import (
    get_llm_client,
    get_paper_text_store,
    get_summary_cache,
)
from app.schemas.summary import SummaryRequest, SummarySchema
from app.services.cache import SummaryCache
from app.services.summarizer import (
    SUMMARY_GENERATION_FAILED_MESSAGE,
    SummaryGenerationError,
    generate_summary,
)
from app.services.summary_service import PaperTextStore

router = APIRouter(prefix="/api", tags=["summary"])


@router.post("/summary", response_model=SummarySchema)
async def get_or_generate_summary(
    request: SummaryRequest,
    raw_request: Request,
    cache: Annotated[SummaryCache, Depends(get_summary_cache)],
    text_store: Annotated[PaperTextStore, Depends(get_paper_text_store)],
) -> SummarySchema:
    """Retrieve cached summary or generate a new structured summary from stored paper text."""
    doc_hash = request.doc_hash

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
    except SummaryGenerationError as exc:
        raise HTTPException(
            status_code=502,
            detail=SUMMARY_GENERATION_FAILED_MESSAGE,
        ) from exc

    # Step 6: Store in cache and return
    cache.set(doc_hash, summary.model_dump())
    return summary
