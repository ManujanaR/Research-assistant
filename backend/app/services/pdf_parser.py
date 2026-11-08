import concurrent.futures
import logging
import os
import re
import tempfile
import time
from collections import Counter
from typing import Any

import ocrmypdf
import pymupdf
from pydantic import BaseModel, Field

from app.core.config import get_settings

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
    ocr_used: bool = False
    header_block: str = ""


def extract_page_1_header(page_1_text: str) -> str:
    """Extract raw text block appearing above the title on Page 1 (e.g. conference headers, organization text)."""
    if not page_1_text:
        return ""

    from app.services.credibility_service import extract_title_from_page_1

    title = extract_title_from_page_1(page_1_text)
    if not title:
        paragraphs = [p.strip() for p in page_1_text.split("\n\n") if p.strip()]
        if len(paragraphs) > 1:
            return paragraphs[0]
        return ""

    title_words = [w for w in re.split(r"\s+", title.strip()) if w]
    prefix = " ".join(title_words[: min(4, len(title_words))])
    idx = page_1_text.lower().find(prefix.lower())
    if idx <= 0:
        idx = page_1_text.lower().find(title.lower())

    if idx > 0:
        return page_1_text[:idx].strip()

    return ""


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
        raw_pages_text: list[str] = []
        total_extracted_len = 0

        for page_index in range(page_count):
            page = doc.load_page(page_index)
            raw_text = page.get_text()
            total_extracted_len += len(raw_text.strip())
            cleaned_text = _clean_glyphs(raw_text)
            raw_pages_text.append(cleaned_text)

            # Lines for header/footer comparison
            lines = [line.strip() for line in cleaned_text.splitlines() if line.strip()]
            raw_pages_lines.append(lines)

        ocr_used = False
        if total_extracted_len == 0:
            settings = get_settings()
            if not settings.ocr_enabled:
                logger.info(
                    "PDF contains 0 extractable text characters across %d pages (OCR disabled)",
                    page_count,
                )
                raise NoExtractableTextError(
                    "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
                )

            # Document has no text on any page; run OCR and re-extract text
            temp_input_path = None
            temp_output_path = None
            start_ocr_time = time.monotonic()
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_in:
                    temp_input_path = f_in.name
                    f_in.write(pdf_bytes)
                    f_in.flush()

                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as f_out:
                    temp_output_path = f_out.name

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        ocrmypdf.ocr,
                        temp_input_path,
                        temp_output_path,
                        skip_text=True,
                        language="eng",
                        output_type="pdf",
                    )
                    future.result(timeout=settings.ocr_timeout_seconds)

                duration = time.monotonic() - start_ocr_time

                if (
                    not os.path.exists(temp_output_path)
                    or os.path.getsize(temp_output_path) == 0
                ):
                    raise NoExtractableTextError(
                        "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
                    )

                with open(temp_output_path, "rb") as f_ocr:
                    ocr_pdf_bytes = f_ocr.read()

                # Re-extract text from OCR result
                doc.close()
                doc = pymupdf.open(stream=ocr_pdf_bytes, filetype="pdf")
                page_count = doc.page_count
                if page_count == 0:
                    raise NoExtractableTextError(
                        "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
                    )

                raw_pages_lines = []
                raw_pages_text = []
                total_extracted_len = 0
                for page_index in range(page_count):
                    page = doc.load_page(page_index)
                    raw_text = page.get_text()
                    total_extracted_len += len(raw_text.strip())
                    cleaned_text = _clean_glyphs(raw_text)
                    raw_pages_text.append(cleaned_text)
                    lines = [
                        line.strip()
                        for line in cleaned_text.splitlines()
                        if line.strip()
                    ]
                    raw_pages_lines.append(lines)

                logger.info(
                    "OCR completed in %.2fs. Page count: %d, character count: %d",
                    duration,
                    page_count,
                    total_extracted_len,
                )

                if total_extracted_len == 0:
                    raise NoExtractableTextError(
                        "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
                    )

                ocr_used = True
            except NoExtractableTextError:
                raise
            except Exception as exc:
                duration = time.monotonic() - start_ocr_time
                logger.warning(
                    "OCR processing failed or timed out after %.2fs (%s)",
                    duration,
                    type(exc).__name__,
                )
                raise NoExtractableTextError(
                    "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
                ) from exc
            finally:
                if temp_input_path and os.path.exists(temp_input_path):
                    try:
                        os.unlink(temp_input_path)
                    except OSError:
                        pass
                if temp_output_path and os.path.exists(temp_output_path):
                    try:
                        os.unlink(temp_output_path)
                    except OSError:
                        pass

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

        page_1_header = ""
        if raw_pages_text:
            page_1_raw_text = raw_pages_text[0]
            page_1_header = extract_page_1_header(page_1_raw_text)

        all_chunks: list[dict[str, Any]] = []

        for page_index in range(page_count):
            page_number = page_index + 1
            lines = raw_pages_lines[page_index]

            filtered_lines = [
                line
                for line in lines
                if (
                    (page_index == 0 and page_1_header and line in page_1_header)
                    or (line not in repeated_headers_footers and not line.isdigit())
                )
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

        # Ingestion Header Retention: ensure raw text block above the title on Page 1 is preserved and prepended
        if page_1_header and all_chunks and page_1_header not in all_chunks[0]["text"]:
            all_chunks[0]["text"] = f"{page_1_header}\n\n{all_chunks[0]['text']}"

        return ParsedDocument(
            page_count=page_count,
            chunks=all_chunks,
            ocr_used=ocr_used,
            header_block=page_1_header,
        )
    finally:
        doc.close()
