"""Document credibility and reporting signals API endpoint."""

import json
import logging
from typing import Annotated

from chromadb.api import ClientAPI
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_chroma_client, get_current_user
from app.db.session import get_db
from app.models.credibility import DocumentCredibility
from app.models.user import User
from app.schemas.credibility import CredibilityResponse, CredibilitySignals
from app.services.ownership_service import is_owner
from app.services.qa import collection_exists

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["credibility"])


@router.get("/{doc_hash}/credibility", response_model=CredibilityResponse)
async def get_document_credibility(
    doc_hash: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    chroma_client: Annotated[ClientAPI, Depends(get_chroma_client)],
) -> CredibilityResponse:
    """Retrieve document credibility score, external database check, and reporting signals."""
    # Step 1: Pre-checks (Ownership & 404)
    if not is_owner(doc_hash, current_user.id, db=db):
        raise HTTPException(
            status_code=404,
            detail="Document not found. Upload the PDF first.",
        )

    if not collection_exists(doc_hash, client=chroma_client):
        raise HTTPException(
            status_code=404,
            detail="Document not found. Upload the PDF first.",
        )

    # Step 2: Query DB record
    record = (
        db.query(DocumentCredibility)
        .filter(DocumentCredibility.doc_hash == doc_hash)
        .first()
    )

    if not record or record.status == "processing":
        return CredibilityResponse(
            status="processing",
            external_check="skipped",
            score=0,
            badge_label="Analyzing signals...",
            badge_variant="neutral",
            signals=CredibilitySignals(),
        )

    try:
        signals_data = json.loads(record.signals_json)
        signals = CredibilitySignals.model_validate(signals_data)
    except (json.JSONDecodeError, ValueError, TypeError):
        signals = CredibilitySignals()

    return CredibilityResponse(
        status=record.status,
        external_check=record.external_check,
        score=record.score,
        badge_label=record.badge_label,
        badge_variant=record.badge_variant,
        signals=signals,
        disclaimer=record.disclaimer,
    )
