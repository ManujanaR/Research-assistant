import logging
import os
import tempfile
from typing import Annotated

import openai
from chromadb.api import ClientAPI
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_chroma_client,
    get_current_user,
    get_embedding_function,
    get_paper_text_store,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.upload import UploadResponse
from app.services.ownership_service import record_owner
from app.services.pdf_parser import (
    NoExtractableTextError,
    PdfParseError,
    parse_pdf,
)
from app.services.qa import EmbedFn, index_document
from app.services.summary_service import PaperTextStore
from app.services.upload_validation import validate_and_hash_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    text_store: Annotated[PaperTextStore, Depends(get_paper_text_store)],
    chroma_client: Annotated[ClientAPI, Depends(get_chroma_client)],
    embed_fn: Annotated[EmbedFn, Depends(get_embedding_function)],
) -> UploadResponse:
    """Accept, validate, parse, index into ChromaDB, and populate paper text store."""
    doc_hash, filename, size_bytes, file_bytes = await validate_and_hash_upload(file)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
        temp_path = temp_file.name
        temp_file.write(file_bytes)
        temp_file.flush()

    try:
        # Parse PDF
        try:
            parsed_doc = parse_pdf(file_bytes)
        except NoExtractableTextError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except PdfParseError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        # Populate paper text store with full extracted text
        full_text = "\n\n".join(chunk["text"] for chunk in parsed_doc.chunks)
        text_store.set_text(doc_hash, full_text)

        # Index in ChromaDB
        try:
            await index_document(
                doc_hash, parsed_doc.chunks, embed_fn, client=chroma_client
            )
        except openai.AuthenticationError as exc:
            logger.warning(
                "AI provider AuthenticationError during upload: status %s",
                getattr(exc, "status_code", 401),
            )
            raise HTTPException(
                status_code=503,
                detail="AI provider authentication failed.",
            ) from exc
        except openai.RateLimitError as exc:
            logger.warning(
                "AI provider RateLimitError during upload: status %s",
                getattr(exc, "status_code", 429),
            )
            raise HTTPException(
                status_code=503,
                detail="AI provider rate limit exceeded.",
            ) from exc
        except (openai.APIConnectionError, openai.APITimeoutError) as exc:
            logger.warning(
                "AI provider connection/timeout error during upload: %s",
                type(exc).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail="AI provider connection or timeout error.",
            ) from exc
        except openai.APIStatusError as exc:
            logger.warning(
                "AI provider APIStatusError during upload: status %s",
                exc.status_code,
            )
            raise HTTPException(
                status_code=502,
                detail=f"The AI provider returned an error (status {exc.status_code}). Check MODEL_NAME and EMBEDDING_MODEL in backend/.env.",
            ) from exc

        # Record document ownership (first uploader remains recorded owner)
        record_owner(doc_hash, current_user.id, db=db)

        return UploadResponse(
            doc_hash=doc_hash,
            filename=filename,
            size_bytes=size_bytes,
            page_count=parsed_doc.page_count,
            chunk_count=len(parsed_doc.chunks),
        )
    finally:
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
