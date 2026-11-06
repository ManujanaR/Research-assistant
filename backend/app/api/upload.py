import os
import tempfile
from typing import Annotated

from chromadb.api import ClientAPI
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.dependencies import (
    get_chroma_client,
    get_embedding_function,
    get_paper_text_store,
)
from app.schemas.upload import UploadResponse
from app.services.pdf_parser import (
    NoExtractableTextError,
    PdfParseError,
    parse_pdf,
)
from app.services.qa import EmbedFn, index_document
from app.services.summary_service import PaperTextStore
from app.services.upload_validation import validate_and_hash_upload

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: Annotated[UploadFile, File()],
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
        await index_document(
            doc_hash, parsed_doc.chunks, embed_fn, client=chroma_client
        )

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
