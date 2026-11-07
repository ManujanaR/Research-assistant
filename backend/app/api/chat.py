import logging
from typing import Annotated, Any

import openai
from chromadb.api import ClientAPI
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.core.dependencies import (
    get_chat_llm_client,
    get_chroma_client,
    get_embedding_function,
)
from app.schemas.chat import ChatRequest
from app.services.qa import (
    EmbeddingDimensionMismatchError,
    EmbedFn,
    assemble_chat_messages,
    collection_exists,
    extract_sources,
    retrieve,
    stream_chat_response,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(
    request: ChatRequest,
    chroma_client: Annotated[ClientAPI, Depends(get_chroma_client)],
    embed_fn: Annotated[EmbedFn, Depends(get_embedding_function)],
    llm_client: Annotated[Any, Depends(get_chat_llm_client)],
) -> StreamingResponse:
    """Stream grounded chat answers with SSE and source citations for an uploaded paper."""
    if not collection_exists(request.doc_hash, client=chroma_client):
        raise HTTPException(
            status_code=404,
            detail="Document not found. Upload the PDF first.",
        )

    try:
        chunks = await retrieve(
            doc_hash=request.doc_hash,
            query=request.message,
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
    sources = extract_sources(relevant_chunks, question=request.message)
    messages = assemble_chat_messages(
        question=request.message,
        history=request.history,
        chunks=relevant_chunks,
    )

    return StreamingResponse(
        stream_chat_response(
            messages=messages,
            sources=sources,
            client=llm_client,
        ),
        media_type="text/event-stream",
    )
