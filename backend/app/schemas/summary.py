from pydantic import BaseModel, ConfigDict, Field, field_validator


class SummarySchema(BaseModel):
    """Structured research paper summary schema with five required sections."""

    model_config = ConfigDict(extra="forbid")

    title_authors_abstract: str = Field(
        ...,
        description="The paper's title, listed authors, and abstract summary.",
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

    @field_validator(
        "title_authors_abstract",
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
