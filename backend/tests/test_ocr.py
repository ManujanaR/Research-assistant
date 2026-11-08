"""Tests for OCR processing of scanned and image-only PDFs."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import chromadb
import pymupdf
import pytest

from app.core.config import get_settings
from app.core.dependencies import get_chroma_client, get_embedding_function
from app.main import app
from app.services.pdf_parser import (
    NoExtractableTextError,
    parse_pdf,
)
from tests.conftest import AuthenticatedTestClient


def create_text_pdf(text: str = "This is a real text-based research paper.") -> bytes:
    """Create in-memory PDF with an extractable text layer."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_scanned_pdf() -> bytes:
    """Create in-memory PDF with zero extractable text (simulating an image scan)."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.draw_rect(
        pymupdf.Rect(50, 50, 200, 200), color=(0, 0, 0), fill=(0.5, 0.5, 0.5)
    )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class DummyEmbedder:
    """Dummy embedder for upload indexing."""

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 8 for _ in texts]


@pytest.fixture
def mock_chroma(tmp_path: Path) -> Generator[chromadb.ClientAPI, None, None]:
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma_ocr_test"))
    embedder = DummyEmbedder()
    app.dependency_overrides[get_chroma_client] = lambda: client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    yield client
    app.dependency_overrides.pop(get_chroma_client, None)
    app.dependency_overrides.pop(get_embedding_function, None)


def test_text_based_pdf_does_not_call_ocr() -> None:
    """A text-based PDF does not call OCR."""
    pdf_bytes = create_text_pdf("Standard extractable text in document.")

    with patch("app.services.pdf_parser.ocrmypdf.ocr") as mock_ocr:
        parsed = parse_pdf(pdf_bytes)
        assert mock_ocr.call_count == 0
        assert parsed.ocr_used is False
        assert len(parsed.chunks) > 0


def test_scanned_pdf_calls_ocr_once_and_text_is_used() -> None:
    """A scanned PDF calls OCR once, and the returned text is used."""
    scanned_bytes = create_scanned_pdf()
    ocr_result_pdf = create_text_pdf(
        "Extracted OCR text describing the methodology and findings."
    )

    def fake_ocr(input_file: str, output_file: str, **kwargs: object) -> None:
        Path(output_file).write_bytes(ocr_result_pdf)

    with patch(
        "app.services.pdf_parser.ocrmypdf.ocr", side_effect=fake_ocr
    ) as mock_ocr:
        parsed = parse_pdf(scanned_bytes)
        assert mock_ocr.call_count == 1
        assert parsed.ocr_used is True
        assert len(parsed.chunks) > 0
        assert any("Extracted OCR text" in c["text"] for c in parsed.chunks)


def test_ocr_returning_no_text_returns_422(
    auth_client: AuthenticatedTestClient, mock_chroma: chromadb.ClientAPI
) -> None:
    """OCR returning no text returns 422 with the exact error message."""
    scanned_bytes = create_scanned_pdf()
    empty_pdf = create_scanned_pdf()

    def fake_ocr_empty(input_file: str, output_file: str, **kwargs: object) -> None:
        Path(output_file).write_bytes(empty_pdf)

    with patch("app.services.pdf_parser.ocrmypdf.ocr", side_effect=fake_ocr_empty):
        # Unit test check
        with pytest.raises(NoExtractableTextError) as exc_info:
            parse_pdf(scanned_bytes)
        assert str(exc_info.value) == (
            "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
        )

        # Upload endpoint check
        response = auth_client.post(
            "/api/upload",
            files={"file": ("empty_scanned.pdf", scanned_bytes, "application/pdf")},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == (
            "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
        )


def test_ocr_timeout_returns_422_and_deletes_temp_files(
    auth_client: AuthenticatedTestClient, mock_chroma: chromadb.ClientAPI
) -> None:
    """OCR timeout returns 422 and deletes the temporary files."""
    scanned_bytes = create_scanned_pdf()

    created_temp_files: list[str] = []

    def fake_ocr_timeout(input_file: str, output_file: str, **kwargs: object) -> None:
        created_temp_files.append(input_file)
        created_temp_files.append(output_file)
        raise TimeoutError("OCR execution timed out")

    with patch("app.services.pdf_parser.ocrmypdf.ocr", side_effect=fake_ocr_timeout):
        response = auth_client.post(
            "/api/upload",
            files={"file": ("scanned_timeout.pdf", scanned_bytes, "application/pdf")},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == (
            "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
        )

        # Check temporary files cleanup
        assert len(created_temp_files) > 0
        for temp_path in created_temp_files:
            assert not Path(temp_path).exists(), (
                f"Temp file was not cleaned up: {temp_path}"
            )


def test_with_ocr_disabled_scanned_pdf_returns_422_without_ocr(
    auth_client: AuthenticatedTestClient,
    mock_chroma: chromadb.ClientAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With OCR_ENABLED=false, a scanned PDF returns 422 and OCR is never called."""
    monkeypatch.setenv("OCR_ENABLED", "false")
    get_settings.cache_clear()

    scanned_bytes = create_scanned_pdf()

    with patch("app.services.pdf_parser.ocrmypdf.ocr") as mock_ocr:
        response = auth_client.post(
            "/api/upload",
            files={"file": ("scanned_disabled.pdf", scanned_bytes, "application/pdf")},
        )
        assert response.status_code == 422
        assert response.json()["detail"] == (
            "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
        )
        assert mock_ocr.call_count == 0

    get_settings.cache_clear()


def test_upload_response_includes_ocr_used_flag(
    auth_client: AuthenticatedTestClient, mock_chroma: chromadb.ClientAPI
) -> None:
    """The upload response includes ocr_used: true when OCR ran, and false otherwise."""
    # 1. Text PDF -> ocr_used: false
    text_bytes = create_text_pdf("Direct text in paper without needing OCR.")
    with patch("app.services.pdf_parser.ocrmypdf.ocr") as mock_ocr:
        resp_text = auth_client.post(
            "/api/upload",
            files={"file": ("text_paper.pdf", text_bytes, "application/pdf")},
        )
        assert resp_text.status_code == 200
        data_text = resp_text.json()
        assert data_text["ocr_used"] is False
        assert mock_ocr.call_count == 0

    # 2. Scanned PDF with mock OCR -> ocr_used: true
    scanned_bytes = create_scanned_pdf()
    ocr_pdf = create_text_pdf("Extracted text through OCR for scanned paper.")

    def fake_ocr(input_file: str, output_file: str, **kwargs: object) -> None:
        Path(output_file).write_bytes(ocr_pdf)

    with patch(
        "app.services.pdf_parser.ocrmypdf.ocr", side_effect=fake_ocr
    ) as mock_ocr:
        resp_scanned = auth_client.post(
            "/api/upload",
            files={"file": ("scanned_paper.pdf", scanned_bytes, "application/pdf")},
        )
        assert resp_scanned.status_code == 200
        data_scanned = resp_scanned.json()
        assert data_scanned["ocr_used"] is True
        assert mock_ocr.call_count == 1
