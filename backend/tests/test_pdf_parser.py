from pathlib import Path

import pymupdf
import pytest

from app.services.pdf_parser import (
    NoExtractableTextError,
    PdfParseError,
    parse_pdf,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_scanned_fixture_raises_no_extractable_text_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a scanned/image-only PDF raises NoExtractableTextError with exact message when OCR is disabled."""
    monkeypatch.setenv("OCR_ENABLED", "false")
    from app.core.config import get_settings

    get_settings.cache_clear()
    scanned_path = FIXTURES_DIR / "sample_scanned.pdf"
    assert scanned_path.exists(), "sample_scanned.pdf fixture must exist"

    scanned_bytes = scanned_path.read_bytes()
    try:
        with pytest.raises(NoExtractableTextError) as exc_info:
            parse_pdf(scanned_bytes)

        assert str(exc_info.value) == (
            "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
        )
    finally:
        get_settings.cache_clear()


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


def test_cleanup_repeated_headers_footers_and_glyphs() -> None:
    """Verify that repeated headers, footers, bare page numbers, and glyph placeholders are removed."""
    doc = pymupdf.open()
    page1 = doc.new_page()
    page1.insert_text(
        (50, 50),
        "International Journal of Computer Science\n\nIntroduction to artificial intelligence with glyph \u25a1 placeholder.\nSecond sentence on page 1.\n\n1",
    )
    page2 = doc.new_page()
    page2.insert_text(
        (50, 50),
        "International Journal of Computer Science\n\nMethodology section discusses deep neural networks.\nSecond sentence on page 2.\n\n2",
    )
    pdf_bytes = doc.tobytes()
    doc.close()

    parsed = parse_pdf(pdf_bytes)
    assert parsed.page_count == 2
    full_text = " ".join(c["text"] for c in parsed.chunks)

    # Repeated header removed
    assert "International Journal of Computer Science" not in full_text
    # Bare page numbers removed
    assert not any(c["text"].strip() == "1" for c in parsed.chunks)
    assert not any(c["text"].strip() == "2" for c in parsed.chunks)
    # Glyph placeholder removed
    assert "\u25a1" not in full_text
    # Core content preserved
    assert "Introduction to artificial intelligence" in full_text
    assert "Methodology section discusses" in full_text


def test_sentence_boundary_chunking_never_cuts_sentences() -> None:
    """Verify that chunks split strictly on sentence boundaries without cutting sentences."""
    sentences = [
        f"Sentence number {i:02d} describes experimental results in full detail."
        for i in range(25)
    ]
    page_content = "\n".join(sentences)

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(page.rect, page_content)
    pdf_bytes = doc.tobytes()
    doc.close()

    parsed = parse_pdf(pdf_bytes)
    assert parsed.page_count == 1
    assert len(parsed.chunks) > 1

    for chunk in parsed.chunks:
        text = chunk["text"].strip()
        # Every chunk starts and ends on a complete sentence boundary
        assert text.startswith("Sentence number ")
        assert text.endswith("in full detail.")


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
