"""Document credibility database model."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DocumentCredibility(Base):
    """Database model for document credibility and reporting signals evaluation."""

    __tablename__ = "document_credibility"

    doc_hash: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="processing",
        nullable=False,
    )
    external_check: Mapped[str] = mapped_column(
        String(20),
        default="skipped",
        nullable=False,
    )
    score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    badge_label: Mapped[str] = mapped_column(
        String(50),
        default="Venue Unverified",
        nullable=False,
    )
    badge_variant: Mapped[str] = mapped_column(
        String(20),
        default="neutral",
        nullable=False,
    )
    signals_json: Mapped[str] = mapped_column(
        Text,
        default="{}",
        nullable=False,
    )
    disclaimer: Mapped[str] = mapped_column(
        Text,
        default=(
            "External metrics verified via OpenAlex Global Academic Registry. "
            "This score reflects structural reporting signals and database records, "
            "not scientific correctness."
        ),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
