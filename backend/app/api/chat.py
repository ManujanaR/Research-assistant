from typing import Annotated, Any

from chromadb.api import ClientAPI
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.dependencies import (
    get_chat_llm_client,
    get_chroma_client,
    get_embedding_function,
)
from app.schemas.chat import ChatRequest
from app.services.qa import (
    EmbedFn,
    assemble_chat_messages,
    collection_exists,
    extract_sources,
    retrieve,
    stream_chat_response,
)

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

    chunks = await retrieve(
        doc_hash=request.doc_hash,
        query=request.message,
        embed_fn=embed_fn,
        top_k=5,
        client=chroma_client,
    )
    sources = extract_sources(chunks)
    messages = assemble_chat_messages(
        question=request.message,
        history=request.history,
        chunks=chunks,
    )

    return StreamingResponse(
        stream_chat_response(
            messages=messages,
            sources=sources,
            client=llm_client,
        ),
        media_type="text/event-stream",
    )
