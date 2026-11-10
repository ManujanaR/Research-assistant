import logging
import re
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
from app.services.metadata_service import get_document_metadata
from app.services.ownership_service import is_owner
from app.services.qa import (
    EmbeddingDimensionMismatchError,
    EmbedFn,
    assemble_chat_messages,
    assemble_overview_messages,
    collection_exists,
    extract_sources,
    get_document_page_count,
    get_title_authors_abstract,
    rebuild_text_from_chroma,
    retrieve,
    retrieve_multi_section,
    stream_chat_response,
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

    # Step 2: Resolve document metadata
    meta = get_document_metadata(request.doc_hash, db=db)
    metadata_dict: dict[str, Any] = {
        "title": meta.title if meta else None,
        "authors": meta.authors if meta else None,
        "detected_publisher": meta.detected_publisher if meta else None,
        "detected_venue": meta.detected_venue if meta else None,
        "publication_year": meta.publication_year if meta else None,
    }

    if not metadata_dict["title"] or not metadata_dict["authors"]:
        from app.core.dependencies import get_summary_cache

        cache = get_summary_cache()
        cached_summary = cache.get(request.doc_hash)
        if cached_summary and isinstance(cached_summary, dict):
            header_info = cached_summary.get("header")
            if isinstance(header_info, dict):
                if not metadata_dict["title"] and header_info.get("title"):
                    metadata_dict["title"] = header_info.get("title")
                if not metadata_dict["authors"] and header_info.get("authors"):
                    metadata_dict["authors"] = header_info.get("authors")
            elif "title_authors_abstract" in cached_summary:
                parts = str(cached_summary["title_authors_abstract"]).split(" - ", 1)
                if not metadata_dict["title"] and len(parts) > 0:
                    metadata_dict["title"] = parts[0].strip()
                if not metadata_dict["authors"] and len(parts) > 1:
                    metadata_dict["authors"] = parts[1].split("\n")[0].strip()

        if not metadata_dict["title"]:
            summary_header = get_title_authors_abstract(request.doc_hash)
            if summary_header:
                metadata_dict["title"] = summary_header

        if metadata_dict["title"] or metadata_dict["authors"]:
            try:
                from app.services.metadata_service import (
                    HeaderMetadata,
                    save_document_metadata,
                )

                save_document_metadata(
                    doc_hash=request.doc_hash,
                    metadata=HeaderMetadata(),
                    title=metadata_dict.get("title"),
                    authors=metadata_dict.get("authors"),
                    db=db,
                )
            except Exception as exc:  # noqa: BLE001
                logger.debug("Silently ignored metadata sync failure: %s", exc)

    # Step 3: Single structured classifier and query rewriter call
    scope = get_title_authors_abstract(request.doc_hash)
    if not scope:
        t = metadata_dict.get("title") or ""
        a = metadata_dict.get("authors") or ""
        if t or a:
            scope = f"{t} by {a}".strip()
    scope = (scope or "").strip()[:1000]

    classification = await classify_and_rewrite(
        message=request.message,
        history=request.history,
        client=llm_client,
        scope=scope,
    )

    # Step 4: Intent routing
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

    # Conversational turns, check-ins, or out-of-scope queries:
    # Always pass metadata and empty chunks into the unified generation call without vector retrieval
    if classification.intent in ("chat", "outside_paper"):
        messages = assemble_chat_messages(
            question=request.message,
            history=request.history,
            chunks=[],
            metadata=metadata_dict,
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

    # Step 5: Intent is "document_question" -> retrieve relevant chunks
    search_query = classification.query.strip() or request.message

    try:
        if classification.is_comparative:
            targets = [
                str(t).strip()
                for t in (classification.comparison_targets or [])
                if t and str(t).strip()
            ]
            if not targets:
                query_source = (classification.query or "").strip() or request.message
                parts = re.split(
                    r"\s+(?:and|vs\.?)\s+|,\s*", query_source, flags=re.IGNORECASE
                )
                cleaned = [
                    re.sub(
                        r"^(?:compare|contrast|evaluate|check)\s+(?:the\s+)?",
                        "",
                        p.strip(),
                        flags=re.IGNORECASE,
                    ).strip()
                    for p in parts
                    if p.strip()
                ]
                targets = [
                    re.sub(r"^the\s+", "", c, flags=re.IGNORECASE).strip()
                    for c in cleaned
                    if c
                ]
            chunks = await retrieve_multi_section(
                doc_hash=request.doc_hash,
                targets=targets,
                embed_fn=embed_fn,
                client=chroma_client,
                top_k=3,
            )
        else:
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
    max_relevant = 6 if classification.is_comparative else 3
    sorted_relevant = sorted(relevant_chunks, key=lambda c: c.distance)[:max_relevant]

    sources = extract_sources(
        sorted_relevant, question=request.message, max_sources=max_relevant
    )
    messages = assemble_chat_messages(
        question=request.message,
        history=request.history,
        chunks=sorted_relevant,
        metadata=metadata_dict,
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
