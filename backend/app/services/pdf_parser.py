import logging
import re
from collections import Counter
from typing import Any

import pymupdf
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

TARGET_CHUNK_SIZE = 800

# Unicode private-use areas and missing-glyph characters:
# U+25A1 ('□'), U+FFFD (''), BMP PUA (U+E000-U+F8FF), Plane 15 (U+F0000-U+FFFFD), Plane 16 (U+100000-U+10FFFD)
GLYPH_CLEANUP_REGEX = re.compile(
    r"[\u25a1\ufffd\ue000-\uf8ff\U000f0000-\U000ffffd\U00100000-\U0010fffd]"
)

# Sentence boundary regex avoiding common abbreviations and list numbers
SENTENCE_SPLIT_REGEX = re.compile(
    r"(?<!\bet al\.)(?<!e\.g\.)(?<!i\.e\.)(?<!\d\.)(?<=[.!?])\s+"
)


class PdfParseError(Exception):
    """Raised when the uploaded file cannot be opened/parsed as a valid PDF."""


class NoExtractableTextError(Exception):
    """Raised when the PDF yields zero extractable text (e.g. scanned or image-only)."""


class ParsedDocument(BaseModel):
    """Container for parsed document pages and page-attributed chunks."""

    page_count: int = Field(..., ge=0)
    chunks: list[dict[str, Any]]


def _clean_glyphs(text: str) -> str:
    """Replace private-use and missing-glyph characters with space and collapse repeated horizontal whitespace."""
    cleaned = GLYPH_CLEANUP_REGEX.sub(" ", text)
    return re.sub(r"[ \t]+", " ", cleaned)


def _split_into_sentences(text: str) -> list[str]:
    """Split text into complete sentences along sentence boundaries."""
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    sentences: list[str] = []
    for para in paragraphs:
        para_norm = " ".join(line.strip() for line in para.splitlines() if line.strip())
        if not para_norm:
            continue
        parts = [s.strip() for s in SENTENCE_SPLIT_REGEX.split(para_norm) if s.strip()]
        if parts:
            sentences.extend(parts)
        else:
            sentences.append(para_norm)

    return sentences


def _chunk_sentences(sentences: list[str], page_number: int) -> list[dict[str, Any]]:
    """Split sentences into chunks along sentence boundaries around TARGET_CHUNK_SIZE."""
    if not sentences:
        return []

    chunks: list[dict[str, Any]] = []
    current_sentences: list[str] = []
    current_len = 0

    for sentence in sentences:
        sent_len = len(sentence)
        delimiter_len = 1 if current_sentences else 0

        if current_sentences and (
            current_len + delimiter_len + sent_len > TARGET_CHUNK_SIZE
        ):
            chunks.append({"text": " ".join(current_sentences), "page": page_number})
            current_sentences = [sentence]
            current_len = sent_len
        else:
            current_sentences.append(sentence)
            current_len += delimiter_len + sent_len

    if current_sentences:
        chunks.append({"text": " ".join(current_sentences), "page": page_number})

    return chunks


def parse_pdf(pdf_bytes: bytes) -> ParsedDocument:
    """Parse a PDF document from raw bytes into cleaned, sentence-attributed text chunks.

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

        raw_pages_lines: list[list[str]] = []
        total_extracted_len = 0

        for page_index in range(page_count):
            page = doc.load_page(page_index)
            raw_text = page.get_text()
            total_extracted_len += len(raw_text.strip())
            cleaned_text = _clean_glyphs(raw_text)

            # Lines for header/footer comparison
            lines = [line.strip() for line in cleaned_text.splitlines() if line.strip()]
            raw_pages_lines.append(lines)

        if total_extracted_len == 0:
            logger.info(
                "PDF contains 0 extractable text characters across %d pages", page_count
            )
            raise NoExtractableTextError(
                "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
            )

        # Detect repeated running headers and footers across pages
        repeated_headers_footers: set[str] = set()
        if page_count > 1:
            candidate_counts: Counter[str] = Counter()
            for lines in raw_pages_lines:
                page_candidates: set[str] = set()
                if len(lines) <= 4:
                    page_candidates.update(lines)
                else:
                    page_candidates.update(lines[:2])
                    page_candidates.update(lines[-2:])
                for cand in page_candidates:
                    candidate_counts[cand] += 1

            repeated_headers_footers = {
                cand
                for cand, count in candidate_counts.items()
                if count > (page_count / 2)
            }

        all_chunks: list[dict[str, Any]] = []

        for page_index in range(page_count):
            page_number = page_index + 1
            lines = raw_pages_lines[page_index]

            filtered_lines = [
                line
                for line in lines
                if line not in repeated_headers_footers and not line.isdigit()
            ]

            if not filtered_lines:
                continue

            page_text = "\n".join(filtered_lines)
            sentences = _split_into_sentences(page_text)
            page_chunks = _chunk_sentences(sentences, page_number)
            all_chunks.extend(page_chunks)

        if not all_chunks:
            raise NoExtractableTextError(
                "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
            )

        return ParsedDocument(page_count=page_count, chunks=all_chunks)
    finally:
        doc.close()
