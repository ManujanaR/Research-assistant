from pydantic import BaseModel


class UploadResponse(BaseModel):
    """Schema for document upload response."""

    doc_hash: str
    filename: str
    size_bytes: int
