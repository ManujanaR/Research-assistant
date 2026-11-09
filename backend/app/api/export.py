"""API router for document export endpoint."""

import logging
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import (
    get_current_user,
    get_paper_text_store,
    get_summary_cache,
)
from app.db.session import get_db
from app.models.credibility import DocumentCredibility
from app.models.document import DocumentMetadata
from app.models.user import User
from app.schemas.export import ExportRequest
from app.services.cache import SummaryCache
from app.services.export_service import build_docx
from app.services.ownership_service import is_owner
from app.services.summary_service import PaperTextStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["export"])

DOCX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
UNKNOWN_DOC_DETAIL = "Document not found. Upload the PDF first."


@router.post("/export")
async def export_report(
    request: ExportRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    cache: Annotated[SummaryCache, Depends(get_summary_cache)],
    text_store: Annotated[PaperTextStore, Depends(get_paper_text_store)],
) -> Response:
    """Export summary and conversation turns to an editable Word document (.docx)."""
    start_time = time.perf_counter()
    doc_hash = request.doc_hash

    # Step 1: Check ownership before reading the summary
    if not is_owner(doc_hash, current_user.id, db=db):
        raise HTTPException(
            status_code=404,
            detail=UNKNOWN_DOC_DETAIL,
        )

    # Step 2: Load summary from existing cache or text-store path
    cached = cache.get(doc_hash)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=UNKNOWN_DOC_DETAIL,
        )

    # Step 3: Query metadata and credibility if present in database
    metadata = (
        db.query(DocumentMetadata).filter(DocumentMetadata.doc_hash == doc_hash).first()
    )
    credibility = (
        db.query(DocumentCredibility)
        .filter(DocumentCredibility.doc_hash == doc_hash)
        .first()
    )

    # Step 4: Resolve page and chunk metrics locally
    pages = 1
    chunks = 0
    try:
        from app.services.qa import (
            get_chroma_collection_name,
            get_document_page_count,
        )

        pages = get_document_page_count(doc_hash)
        import chromadb
        from chromadb.errors import ChromaError

        settings = get_settings()
        client = chromadb.PersistentClient(path=settings.chroma_dir)
        coll = client.get_collection(get_chroma_collection_name(doc_hash))
        chunks = coll.count()
    except (
        ChromaError,
        ValueError,
        KeyError,
        OSError,
        RuntimeError,
        AttributeError,
    ) as exc:
        logger.debug(
            "Local doc_metrics resolution fallback for %s: %s", doc_hash[:8], exc
        )

    doc_metrics = {"pages": pages, "chunks": chunks}

    # Step 5: Build Word document (.docx) in memory
    paper_filename = f"{doc_hash[:8]}.pdf"
    date_str = datetime.now(UTC).strftime("%B %d, %Y")
    docx_bytes = build_docx(
        summary=cached,
        filename=paper_filename,
        date=date_str,
        messages=request.messages,
        doc_metrics=doc_metrics,
        credibility=credibility,
        metadata=metadata,
    )

    duration = time.perf_counter() - start_time
    # Security requirement: Never log document text or chat transcripts
    logger.info(
        "Export generated for doc_hash=%s: messages=%d, duration=%.4fs",
        doc_hash[:8],
        len(request.messages),
        duration,
    )

    attachment_filename = f"research-report-{doc_hash[:8]}.docx"
    return Response(
        content=docx_bytes,
        media_type=DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{attachment_filename}"',
        },
    )
