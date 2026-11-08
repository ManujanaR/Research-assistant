"""Schemas for document export."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.cache import HEX_SHA256_PATTERN


class ExportSource(BaseModel):
    """Source reference for an exported assistant answer."""

    model_config = ConfigDict(extra="forbid")

    page_number: int | None = Field(
        default=None,
        description="Page number of the retrieved source chunk.",
    )
    snippet: str | None = Field(
        default=None,
        max_length=200,
        description="Snippet of the retrieved source chunk, at most 200 characters.",
    )


class ExportMessage(BaseModel):
    """A single conversation turn in the export request."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"] = Field(
        ...,
        description="Role of the turn author, either 'user' or 'assistant'.",
    )
    text: str = Field(
        ...,
        max_length=4000,
        description="Message content, at most 4000 characters.",
    )
    sources: list[ExportSource] = Field(
        default_factory=list,
        description="List of optional sources associated with the turn.",
    )


class ExportRequest(BaseModel):
    """Request payload for exporting summary and conversation to .docx."""

    model_config = ConfigDict(extra="forbid")

    doc_hash: str = Field(
        ...,
        description="64-character lowercase hexadecimal SHA-256 hash of the paper.",
    )
    messages: list[ExportMessage] = Field(
        default_factory=list,
        max_length=200,
        description="Conversation turns to export, up to 200 messages.",
    )

    @field_validator("doc_hash")
    @classmethod
    def validate_doc_hash(cls, value: str) -> str:
        """Validate that doc_hash is strictly 64 lowercase hexadecimal characters."""
        if not isinstance(value, str) or not HEX_SHA256_PATTERN.match(value):
            raise ValueError(f"Invalid SHA-256 hash: {value!r}")
        return value
