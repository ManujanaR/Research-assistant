import logging
from typing import Annotated, Any

import openai
from chromadb.api import ClientAPI
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import (
    get_chat_llm_client,
    get_chroma_client,
    get_current_user,
    get_embedding_function,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.services.classifier import classify_and_rewrite
from app.services.ownership_service import is_owner
from app.services.qa import (
    FALLBACK_GROUNDING_MESSAGE,
    OUTSIDE_PAPER_REFUSAL,
    EmbeddingDimensionMismatchError,
    EmbedFn,
    assemble_chat_messages,
    assemble_conversational_messages,
    assemble_overview_messages,
    collection_exists,
    extract_sources,
    get_document_page_count,
    get_title_authors_abstract,
    rebuild_text_from_chroma,
    retrieve,
    stream_chat_response,
    stream_static_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    chroma_client: Annotated[ClientAPI, Depends(get_chroma_client)],
    embed_fn: Annotated[EmbedFn, Depends(get_embedding_function)],
    llm_client: Annotated[Any, Depends(get_chat_llm_client)],
) -> StreamingResponse:
    """Stream grounded chat answers with SSE and source citations for an uploaded paper."""
    # Step 1: Pre-checks: Ownership check & collection check run first before any model call
    if not is_owner(request.doc_hash, current_user.id, db=db):
        raise HTTPException(
            status_code=404,
            detail="Document not found. Upload the PDF first.",
        )

    if not collection_exists(request.doc_hash, client=chroma_client):
        raise HTTPException(
            status_code=404,
            detail="Document not found. Upload the PDF first.",
        )

    # Step 2: Single structured classifier and query rewriter call
    classification = await classify_and_rewrite(
        message=request.message,
        history=request.history,
        client=llm_client,
    )

    # Step 3: Intent execution
    if classification.intent == "chat":
        messages = assemble_conversational_messages(
            message=request.message,
            history=request.history,
        )
        return StreamingResponse(
            stream_chat_response(
                messages=messages,
                sources=[],
                client=llm_client,
                question=request.message,
            ),
            media_type="text/event-stream",
        )

    if classification.intent == "outside_paper":
        return StreamingResponse(
            stream_static_message(OUTSIDE_PAPER_REFUSAL),
            media_type="text/event-stream",
        )

    if classification.intent == "document_overview":
        page_count = get_document_page_count(request.doc_hash, client=chroma_client)
        if page_count > 30:
            overview_text = get_title_authors_abstract(request.doc_hash)
            if not overview_text:
                overview_text = (
                    rebuild_text_from_chroma(request.doc_hash, client=chroma_client)
                    or ""
                )
        else:
            overview_text = rebuild_text_from_chroma(
                request.doc_hash, client=chroma_client
            ) or get_title_authors_abstract(request.doc_hash)

        messages = assemble_overview_messages(
            message=request.message,
            history=request.history,
            context_text=overview_text,
        )
        return StreamingResponse(
            stream_chat_response(
                messages=messages,
                sources=[],
                client=llm_client,
                question=request.message,
            ),
            media_type="text/event-stream",
        )

    # Step 4: Intent is "document_question"
    search_query = classification.query.strip() or request.message

    try:
        chunks = await retrieve(
            doc_hash=request.doc_hash,
            query=search_query,
            embed_fn=embed_fn,
            top_k=5,
            client=chroma_client,
        )
    except EmbeddingDimensionMismatchError as exc:
        raise HTTPException(
            status_code=409,
            detail="The document index was built with a different embedding model. Re-upload the paper to rebuild it.",
        ) from exc
    except openai.AuthenticationError as exc:
        logger.warning(
            "AI provider AuthenticationError during chat retrieval: status %s",
            getattr(exc, "status_code", 401),
        )
        raise HTTPException(
            status_code=503,
            detail="AI provider authentication failed.",
        ) from exc
    except openai.RateLimitError as exc:
        logger.warning(
            "AI provider RateLimitError during chat retrieval: status %s",
            getattr(exc, "status_code", 429),
        )
        raise HTTPException(
            status_code=503,
            detail="AI provider rate limit exceeded.",
        ) from exc
    except (openai.APIConnectionError, openai.APITimeoutError) as exc:
        logger.warning(
            "AI provider connection/timeout error during chat retrieval: %s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="AI provider connection or timeout error.",
        ) from exc
    except openai.APIStatusError as exc:
        logger.warning(
            "AI provider APIStatusError during chat retrieval: status %s",
            exc.status_code,
        )
        raise HTTPException(
            status_code=502,
            detail=f"The AI provider returned an error (status {exc.status_code}). Check MODEL_NAME and EMBEDDING_MODEL in backend/.env.",
        ) from exc

    settings = get_settings()
    relevant_chunks = [
        c for c in chunks if c.distance <= settings.citation_max_distance
    ]
    sorted_relevant = sorted(relevant_chunks, key=lambda c: c.distance)[:3]

    if not sorted_relevant:
        return StreamingResponse(
            stream_static_message(FALLBACK_GROUNDING_MESSAGE),
            media_type="text/event-stream",
        )

    sources = extract_sources(sorted_relevant, question=request.message, max_sources=3)
    messages = assemble_chat_messages(
        question=request.message,
        history=request.history,
        chunks=sorted_relevant,
    )

    return StreamingResponse(
        stream_chat_response(
            messages=messages,
            sources=sources,
            client=llm_client,
            question=request.message,
        ),
        media_type="text/event-stream",
    )
