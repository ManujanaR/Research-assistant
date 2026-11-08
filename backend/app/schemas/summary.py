from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.services.cache import HEX_SHA256_PATTERN


class SummaryRequest(BaseModel):
    """Request schema for retrieving or generating a paper summary."""

    doc_hash: str = Field(
        ...,
        description="64-character lowercase hexadecimal SHA-256 hash of the uploaded paper.",
    )

    @field_validator("doc_hash")
    @classmethod
    def validate_doc_hash(cls, value: str) -> str:
        """Validate that doc_hash is strictly 64 lowercase hexadecimal characters."""
        if not isinstance(value, str) or not HEX_SHA256_PATTERN.match(value):
            raise ValueError(f"Invalid SHA-256 hash: {value!r}")
        return value


class SummaryHeader(BaseModel):
    """Structured paper header containing title, authors, and abstract."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., description="The paper's title.")
    authors: str = Field(..., description="The listed authors of the paper.")
    abstract: str = Field(..., description="The paper's abstract summary.")

    @field_validator("title", "authors", "abstract")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        """Reject empty or whitespace-only strings."""
        if not value or not value.strip():
            raise ValueError(
                "Field must not be empty or whitespace-only. "
                "If not stated in the paper, use 'Not stated in the paper.'"
            )
        return value


class SummarySchema(BaseModel):
    """Structured research paper summary schema with five required sections."""

    model_config = ConfigDict(extra="forbid")

    header: SummaryHeader = Field(
        ...,
        description="Structured paper header containing title, authors, and abstract.",
    )
    problem_statement: str = Field(
        ...,
        description="The primary research question, gap, or challenge addressed.",
    )
    methodology: str = Field(
        ...,
        description="The core approach, dataset, architecture, or experimental setup.",
    )
    key_results: str = Field(
        ...,
        description="Main findings, metrics, comparisons, or empirical discoveries.",
    )
    conclusion: str = Field(
        ...,
        description="Takeaways, conclusions, implications, and future work.",
    )

    @property
    def title_authors_abstract(self) -> str:
        """Backward-compatible string representation for internal services."""
        return f"{self.header.title} - {self.header.authors}\n\n{self.header.abstract}"

    @field_validator(
        "problem_statement",
        "methodology",
        "key_results",
        "conclusion",
    )
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        """Reject empty or whitespace-only strings unless exactly 'Not stated in the paper.'."""
        if not value or not value.strip():
            raise ValueError(
                "Field must not be empty or whitespace-only. "
                "If not stated in the paper, use 'Not stated in the paper.'"
            )
        return value
