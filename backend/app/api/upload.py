from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from app.schemas.upload import UploadResponse
from app.services.upload_validation import validate_and_hash_upload

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: Annotated[UploadFile, File()],
) -> UploadResponse:
    """Accept and validate a single PDF research paper upload."""
    return await validate_and_hash_upload(file)
