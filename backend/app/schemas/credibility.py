"""Pydantic schemas for document credibility and reporting signals."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CredibilitySignals(BaseModel):
    """Detailed structural and external signals breakdown."""

    model_config = ConfigDict(extra="ignore")

    has_doi: bool = False
    doi: str | None = None
    matched_venue: str | None = None
    title_similarity: float = 0.0
    citation_count: int = 0
    reference_count_estimated: int = 0
    is_reference_count_estimated: bool = True
    author_academic_affiliation: bool = False
    has_limitations_section: bool = False
    open_artifacts_detected: bool = False


class CredibilityResponse(BaseModel):
    """API response schema for document credibility evaluation."""

    model_config = ConfigDict(extra="ignore")

    status: Literal["completed", "processing", "failed"] = "processing"
    external_check: Literal["matched", "not_matched", "skipped", "error"] = "skipped"
    score: int = 0
    badge_label: str = "Venue Unverified"
    badge_variant: Literal["success", "warning", "neutral"] = "neutral"
    signals: CredibilitySignals = Field(default_factory=CredibilitySignals)
    disclaimer: str = (
        "This score reflects structural reporting signals and database matches, "
        "not scientific validity."
    )
