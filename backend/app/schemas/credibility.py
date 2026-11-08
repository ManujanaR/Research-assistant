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
    structure_sections_found: int = 0

    # Points breakdown for UI checklist
    venue_points: int = 0
    citation_points: int = 0
    reference_points: int = 0
    affiliation_points: int = 0
    structure_points: int = 0
    bonus_points: int = 0

    # Aliases for frontend compatibility
    estimated_references: int = 0
    recorded_citations: int = 0
    has_academic_affiliation: bool = False


class CredibilityResponse(BaseModel):
    """API response schema for document credibility evaluation."""

    model_config = ConfigDict(extra="ignore")

    status: Literal["completed", "processing", "failed"] = "processing"
    external_check: Literal["matched", "not_matched", "skipped", "error"] = "skipped"
    score: int = 0
    badge_label: str = "Unindexed Draft"
    badge_variant: Literal["success", "warning", "neutral"] = "neutral"
    signals: CredibilitySignals = Field(default_factory=CredibilitySignals)
    disclaimer: str = (
        "External metrics verified via OpenAlex Global Academic Registry. "
        "This score reflects structural reporting signals and database records, "
        "not scientific correctness."
    )
