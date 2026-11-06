from pathlib import Path

import pymupdf
import pytest

from app.services.pdf_parser import (
    NoExtractableTextError,
    PdfParseError,
    parse_pdf,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_scanned_fixture_raises_no_extractable_text_error() -> None:
    """Verify that a scanned/image-only PDF raises NoExtractableTextError with exact message."""
    scanned_path = FIXTURES_DIR / "sample_scanned.pdf"
    assert scanned_path.exists(), "sample_scanned.pdf fixture must exist"

    scanned_bytes = scanned_path.read_bytes()
    with pytest.raises(NoExtractableTextError) as exc_info:
        parse_pdf(scanned_bytes)

    assert str(exc_info.value) == (
        "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
    )


def test_corrupt_input_raises_pdf_parse_error() -> None:
    """Verify that corrupt or non-PDF bytes raise PdfParseError with exact message."""
    with pytest.raises(PdfParseError) as exc_info:
        parse_pdf(b"not a pdf")

    assert str(exc_info.value) == "The uploaded file could not be parsed as a PDF."


def test_chunking_with_in_memory_two_page_pdf() -> None:
    """Verify page-aware chunking on an in-memory 2-page PDF.

    Asserts:
      - page_count == 2
      - every chunk has page >= 1
      - chunks from page 1 never contain page 2's text
      - chunks from page 2 never contain page 1's text
    """
    doc = pymupdf.open()
    page1 = doc.new_page()
    page1.insert_text(
        (50, 50),
        "Page 1 Content Paragraph 1.\n\nPage 1 Content Paragraph 2.",
    )
    page2 = doc.new_page()
    page2.insert_text(
        (50, 50),
        "Page 2 Distinct Text Alpha.\n\nPage 2 Distinct Text Beta.",
    )
    pdf_bytes = doc.tobytes()
    doc.close()

    parsed = parse_pdf(pdf_bytes)
    assert parsed.page_count == 2
    assert len(parsed.chunks) >= 2

    page_1_chunks = [c for c in parsed.chunks if c["page"] == 1]
    page_2_chunks = [c for c in parsed.chunks if c["page"] == 2]

    assert len(page_1_chunks) > 0
    assert len(page_2_chunks) > 0

    for chunk in parsed.chunks:
        assert chunk["page"] >= 1

    for chunk in page_1_chunks:
        assert "Page 2" not in chunk["text"]
        assert "Page 1" in chunk["text"]

    for chunk in page_2_chunks:
        assert "Page 1" not in chunk["text"]
        assert "Page 2" in chunk["text"]


def test_sample_short_pdf_placeholder() -> None:
    """Placeholder test for sample_short.pdf to be supplied by user."""
    short_path = FIXTURES_DIR / "sample_short.pdf"
    if not short_path.exists():
        pytest.skip("sample_short.pdf fixture pending supply by user")

    parsed = parse_pdf(short_path.read_bytes())
    assert parsed.page_count > 0
    assert len(parsed.chunks) > 0


def test_sample_standard_pdf_placeholder() -> None:
    """Placeholder test for sample_standard.pdf to be supplied by user."""
    standard_path = FIXTURES_DIR / "sample_standard.pdf"
    if not standard_path.exists():
        pytest.skip("sample_standard.pdf fixture pending supply by user")

    parsed = parse_pdf(standard_path.read_bytes())
    assert parsed.page_count > 0
    assert len(parsed.chunks) > 0
