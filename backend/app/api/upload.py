import logging
import os
import tempfile
from typing import Annotated, Any

import openai
from chromadb.api import ClientAPI
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.core.dependencies import (
    get_chat_llm_client,
    get_chroma_client,
    get_current_user,
    get_embedding_function,
    get_paper_text_store,
)
from app.db.session import SessionLocal, get_db
from app.models.credibility import DocumentCredibility
from app.models.user import User
from app.schemas.upload import UploadResponse
from app.services.credibility_service import evaluate_document_credibility
from app.services.metadata_service import (
    extract_header_metadata,
    save_document_metadata,
)
from app.services.ownership_service import record_owner
from app.services.pdf_parser import (
    NoExtractableTextError,
    PdfParseError,
    parse_pdf,
)
from app.services.qa import (
    EmbedFn,
    get_chroma_collection_name,
    get_document_page_count,
    index_document,
)
from app.services.summary_service import PaperTextStore
from app.services.upload_validation import validate_and_hash_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["upload"])


async def run_credibility_in_background(
    doc_hash: str, page_1_text: str, full_text: str
) -> None:
    """Run non-blocking credibility evaluation in background task."""
    db = SessionLocal()
    try:
        await evaluate_document_credibility(
            doc_hash=doc_hash,
            db=db,
            page_1_text=page_1_text,
            full_text=full_text,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Background credibility task failed for %s: %s", doc_hash, exc)
    finally:
        db.close()


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    text_store: Annotated[PaperTextStore, Depends(get_paper_text_store)],
    chroma_client: Annotated[ClientAPI, Depends(get_chroma_client)],
    embed_fn: Annotated[EmbedFn, Depends(get_embedding_function)],
    background_tasks: BackgroundTasks,
    llm_client: Annotated[Any, Depends(get_chat_llm_client)],
) -> UploadResponse:
    """Accept, validate, parse, index into ChromaDB, and populate paper text store."""
    doc_hash, filename, size_bytes, file_bytes = await validate_and_hash_upload(file)

    # Step 1: Storage Deduplication Check
    # If the hash already has a Chroma index and parsed text, reuse them.
    # Skip re-parsing, re-embedding, and re-summarising.
    coll_name = get_chroma_collection_name(doc_hash)
    existing_collection = None
    try:
        existing_collection = chroma_client.get_collection(name=coll_name)
    except Exception:  # noqa: BLE001
        existing_collection = None

    if existing_collection is not None and existing_collection.count() > 0:
        existing_text = text_store.get_text(doc_hash)
        if existing_text:
            logger.info(
                "Reusing existing storage for doc_hash=%s; skipping parse and embed",
                doc_hash,
            )
            # Create an ownership row for the uploading account only
            record_owner(doc_hash, current_user.id, db=db)

            # Ensure credibility record exists
            cred_record = (
                db.query(DocumentCredibility)
                .filter(DocumentCredibility.doc_hash == doc_hash)
                .first()
            )
            if not cred_record:
                cred_record = DocumentCredibility(
                    doc_hash=doc_hash, status="processing"
                )
                db.add(cred_record)
                db.commit()

            coll_meta = existing_collection.metadata or {}
            chunk_count = existing_collection.count()
            page_count = coll_meta.get("page_count")
            if not page_count or not isinstance(page_count, int):
                page_count = get_document_page_count(doc_hash, client=chroma_client)
            ocr_used = bool(coll_meta.get("ocr_used", False))

            return UploadResponse(
                doc_hash=doc_hash,
                filename=filename,
                size_bytes=size_bytes,
                page_count=int(page_count),
                chunk_count=chunk_count,
                ocr_used=ocr_used,
            )

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

        # Dynamic header metadata extraction (fails safely to nulls)
        header_metadata = await extract_header_metadata(
            parsed_doc.header_block, client=llm_client
        )
        save_document_metadata(
            doc_hash=doc_hash,
            metadata=header_metadata,
            header_text=parsed_doc.header_block,
            db=db,
        )

        # Populate paper text store with full extracted text
        full_text = "\n\n".join(chunk["text"] for chunk in parsed_doc.chunks)
        text_store.set_text(doc_hash, full_text)

        # Index in ChromaDB
        try:
            await index_document(
                doc_hash,
                parsed_doc.chunks,
                embed_fn,
                client=chroma_client,
                page_count=parsed_doc.page_count,
                ocr_used=parsed_doc.ocr_used,
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

        # Trigger non-blocking credibility evaluation in background task
        # Scan Page 1 and Page 2 for front matter (e.g. titles, author contact emails, affiliations)
        page_1_and_2_text = "\n\n".join(
            c["text"] for c in parsed_doc.chunks if c.get("page") in (1, 2)
        )
        cred_record = (
            db.query(DocumentCredibility)
            .filter(DocumentCredibility.doc_hash == doc_hash)
            .first()
        )
        if not cred_record:
            cred_record = DocumentCredibility(doc_hash=doc_hash, status="processing")
            db.add(cred_record)
            db.commit()

        background_tasks.add_task(
            run_credibility_in_background,
            doc_hash=doc_hash,
            page_1_text=page_1_and_2_text,
            full_text=full_text,
        )

        return UploadResponse(
            doc_hash=doc_hash,
            filename=filename,
            size_bytes=size_bytes,
            page_count=parsed_doc.page_count,
            chunk_count=len(parsed_doc.chunks),
            ocr_used=parsed_doc.ocr_used,
        )
    finally:
        if os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
