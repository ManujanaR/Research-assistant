import hashlib
import logging

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings
from app.schemas.upload import UploadResponse

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024  # 64 KB read buffer


async def validate_and_hash_upload(file: UploadFile) -> UploadResponse:
    """Validate PDF MIME type, file extension, enforce size limit in chunks, and compute SHA-256."""
    settings = get_settings()

    filename = file.filename or ""
    content_type = file.content_type or ""

    if content_type != "application/pdf" or not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=415,
            detail="Invalid file type: only application/pdf is accepted.",
        )

    max_bytes = settings.max_upload_mb * 1024 * 1024
    total_size = 0
    hasher = hashlib.sha256()

    while True:
        chunk = await file.read(CHUNK_SIZE)
        if not chunk:
            break
        total_size += len(chunk)
        if total_size > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed size of {settings.max_upload_mb}MB.",
            )
        hasher.update(chunk)

    doc_hash = hasher.hexdigest()
    logger.debug(
        "Validated upload: filename=%s, size=%d bytes, hash=%s",
        filename,
        total_size,
        doc_hash,
    )

    return UploadResponse(
        doc_hash=doc_hash,
        filename=filename,
        size_bytes=total_size,
    )
