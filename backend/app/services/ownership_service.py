"""Service for recording and verifying document ownership."""

import logging

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.document import DocumentOwnership

logger = logging.getLogger(__name__)


def record_owner(
    doc_hash: str | Session,
    user_id: str,
    db: Session | None = None,
) -> DocumentOwnership:
    """Record the owner of a document if not already recorded.

    If a document was already uploaded by a user, ownership remains with the first owner.
    Supports either (doc_hash, user_id, db=None) or (db, doc_hash, user_id).
    """
    if isinstance(doc_hash, Session):
        session = doc_hash
        target_hash = user_id
        target_user_id = str(db) if db is not None else ""
        should_close = False
    else:
        target_hash = doc_hash
        target_user_id = user_id
        session = db
        should_close = False

    if session is None:
        session = SessionLocal()
        should_close = True

    try:
        existing = (
            session.query(DocumentOwnership)
            .filter(DocumentOwnership.doc_hash == target_hash)
            .first()
        )
        if existing is not None:
            # First owner remains recorded; do not transfer ownership
            return existing

        ownership = DocumentOwnership(
            doc_hash=target_hash,
            owner_id=target_user_id,
        )
        session.add(ownership)
        session.commit()
        session.refresh(ownership)
        logger.info(
            "Recorded ownership for doc_hash=%s to owner_id=%s",
            target_hash,
            target_user_id,
        )
        return ownership
    finally:
        if should_close:
            session.close()


def is_owner(
    doc_hash: str | Session,
    user_id: str,
    db: Session | None = None,
) -> bool:
    """Check if the user is the recorded owner of the given document hash.

    Supports either (doc_hash, user_id, db=None) or (db, doc_hash, user_id).
    """
    if isinstance(doc_hash, Session):
        session = doc_hash
        target_hash = user_id
        target_user_id = str(db) if db is not None else ""
        should_close = False
    else:
        target_hash = doc_hash
        target_user_id = user_id
        session = db
        should_close = False

    if session is None:
        session = SessionLocal()
        should_close = True

    try:
        existing = (
            session.query(DocumentOwnership)
            .filter(DocumentOwnership.doc_hash == target_hash)
            .first()
        )
        if existing is None:
            return False
        return existing.owner_id == target_user_id
    finally:
        if should_close:
            session.close()
