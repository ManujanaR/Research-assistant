from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.cache import HEX_SHA256_PATTERN


class ChatMessage(BaseModel):
    """A single turn in the chat history."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"] = Field(
        ...,
        description="Role of the message sender, either user or assistant.",
    )
    content: str = Field(
        ...,
        max_length=4000,
        description="Content of the chat message (max 4000 characters).",
    )


class ChatRequest(BaseModel):
    """Request schema for querying the uploaded paper via chat."""

    model_config = ConfigDict(extra="forbid")

    doc_hash: str = Field(
        ...,
        description="64-character lowercase hexadecimal SHA-256 hash of the document.",
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Current user question (1 to 2000 characters).",
    )
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Prior conversation history turns.",
    )

    @field_validator("doc_hash")
    @classmethod
    def validate_doc_hash(cls, value: str) -> str:
        """Validate that doc_hash is strictly 64 lowercase hexadecimal characters."""
        if not isinstance(value, str) or not HEX_SHA256_PATTERN.match(value):
            raise ValueError(f"Invalid SHA-256 hash: {value!r}")
        return value


class ChatSource(BaseModel):
    """Source citation snippet and page provenance from retrieved chunks."""

    model_config = ConfigDict(extra="forbid")

    page_number: int | None = Field(
        default=None,
        description="Page number where the source excerpt was found.",
    )
    snippet: str = Field(
        ...,
        max_length=200,
        description="Exact excerpt substring from the chunk (max 200 characters).",
    )
