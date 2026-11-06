import logging
from typing import Any

import pymupdf
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

TARGET_CHUNK_SIZE = 800


class PdfParseError(Exception):
    """Raised when the uploaded file cannot be opened/parsed as a valid PDF."""


class NoExtractableTextError(Exception):
    """Raised when the PDF yields zero extractable text (e.g. scanned or image-only)."""


class ParsedDocument(BaseModel):
    """Container for parsed document pages and page-attributed chunks."""

    page_count: int = Field(..., ge=0)
    chunks: list[dict[str, Any]]


def _chunk_page_text(page_text: str, page_number: int) -> list[dict[str, Any]]:
    """Split a single page's text into roughly 800-character chunks along paragraph boundaries."""
    paragraphs = [p.strip() for p in page_text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in page_text.split("\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[dict[str, Any]] = []
    current_chunk_parts: list[str] = []
    current_length = 0

    for para in paragraphs:
        if len(para) > TARGET_CHUNK_SIZE:
            if current_chunk_parts:
                chunks.append(
                    {"text": "\n\n".join(current_chunk_parts), "page": page_number}
                )
                current_chunk_parts = []
                current_length = 0

            for i in range(0, len(para), TARGET_CHUNK_SIZE):
                sub_para = para[i : i + TARGET_CHUNK_SIZE].strip()
                if sub_para:
                    chunks.append({"text": sub_para, "page": page_number})
            continue

        delimiter_len = 2 if current_chunk_parts else 0
        if current_length + len(para) + delimiter_len > TARGET_CHUNK_SIZE:
            if current_chunk_parts:
                chunks.append(
                    {"text": "\n\n".join(current_chunk_parts), "page": page_number}
                )
            current_chunk_parts = [para]
            current_length = len(para)
        else:
            current_chunk_parts.append(para)
            current_length += len(para) + delimiter_len

    if current_chunk_parts:
        chunks.append({"text": "\n\n".join(current_chunk_parts), "page": page_number})

    return chunks


def parse_pdf(pdf_bytes: bytes) -> ParsedDocument:
    """Parse a PDF document from raw bytes into page-attributed text chunks.

    Raises:
        PdfParseError: If the document is corrupt or cannot be opened.
        NoExtractableTextError: If the PDF contains no extractable text.
    """
    try:
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        logger.warning("Failed to open PDF stream: %s", exc)
        raise PdfParseError("The uploaded file could not be parsed as a PDF.") from exc

    try:
        page_count = doc.page_count
        if page_count == 0:
            raise NoExtractableTextError(
                "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
            )

        all_chunks: list[dict[str, Any]] = []
        total_extracted_text = ""

        for page_index in range(page_count):
            page = doc.load_page(page_index)
            page_text = page.get_text()
            total_extracted_text += page_text

            page_number = page_index + 1  # 1-indexed
            page_chunks = _chunk_page_text(page_text, page_number)
            all_chunks.extend(page_chunks)

        if not total_extracted_text.strip():
            logger.info(
                "PDF contains 0 extractable text characters across %d pages", page_count
            )
            raise NoExtractableTextError(
                "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
            )

        return ParsedDocument(page_count=page_count, chunks=all_chunks)
    finally:
        doc.close()
