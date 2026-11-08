"""Document ownership database model."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
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


class DocumentMetadata(Base):
    """Document metadata extracted during ingestion and summaries."""

    __tablename__ = "document_metadata"

    doc_hash: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        index=True,
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    authors: Mapped[str | None] = mapped_column(String(500), nullable=True)
    detected_publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detected_venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    publication_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    header_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
