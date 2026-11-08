from pydantic import BaseModel, Field


class UploadResponse(BaseModel):
    """Schema for document upload response."""

    doc_hash: str = Field(
        ..., description="SHA-256 hash of the uploaded document bytes."
    )
    filename: str = Field(..., description="Original filename of the uploaded PDF.")
    size_bytes: int = Field(
        ..., description="Total size in bytes of the uploaded file."
    )
    page_count: int = Field(default=0, description="Total number of pages parsed.")
    chunk_count: int = Field(default=0, description="Total number of chunks indexed.")
    ocr_used: bool = Field(
        default=False, description="Whether OCR was used to extract text."
    )
