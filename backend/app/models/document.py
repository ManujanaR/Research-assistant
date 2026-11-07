"""Document ownership database model."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DocumentOwnership(Base):
    """DocumentOwnership table mapping doc_hash to user owner_id."""

    __tablename__ = "document_ownership"

    doc_hash: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        index=True,
        nullable=False,
    )
    owner_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
