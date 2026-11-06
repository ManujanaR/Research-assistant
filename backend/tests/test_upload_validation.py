import hashlib
from collections.abc import Generator
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.dependencies import get_chroma_client, get_embedding_function
from app.main import app

client = TestClient(app)


def make_valid_pdf_bytes(text: str = "Valid research paper content") -> bytes:
    """Generate minimal valid PDF bytes with extractable text."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), text)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture(autouse=True)
def override_chroma_and_embed(
    tmp_path: Path,
) -> Generator[None, None, None]:
    """Provide isolated ephemeral Chroma client and dummy embedding function for tests."""
    import chromadb

    test_chroma = chromadb.PersistentClient(path=str(tmp_path / ".chroma"))

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[0.1] * 128 for _ in texts]

    app.dependency_overrides[get_chroma_client] = lambda: test_chroma
    app.dependency_overrides[get_embedding_function] = lambda: fake_embed

    yield

    app.dependency_overrides.clear()


def test_upload_invalid_content_type() -> None:
    """Verify that a non-PDF content type returns HTTP 415."""
    payload = b"%PDF-1.4 test"
    response = client.post(
        "/api/upload",
        files={"file": ("document.pdf", payload, "text/plain")},
    )
    assert response.status_code == 415
    assert response.json() == {
        "detail": "Invalid file type: only application/pdf is accepted."
    }


def test_upload_invalid_extension() -> None:
    """Verify that a non-PDF extension returns HTTP 415 even with application/pdf MIME type."""
    payload = b"%PDF-1.4 test"
    response = client.post(
        "/api/upload",
        files={"file": ("paper.txt", payload, "application/pdf")},
    )
    assert response.status_code == 415
    assert response.json() == {
        "detail": "Invalid file type: only application/pdf is accepted."
    }


def test_upload_case_insensitive_extension() -> None:
    """Verify that uppercase .PDF extension is accepted and returns HTTP 200."""
    payload = make_valid_pdf_bytes("Uppercase PDF extension test")
    response = client.post(
        "/api/upload",
        files={"file": ("paper.PDF", payload, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "paper.PDF"
    assert data["size_bytes"] == len(payload)
    assert data["doc_hash"] == hashlib.sha256(payload).hexdigest()


def test_upload_exceeds_size_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that a payload exceeding MAX_UPLOAD_MB returns HTTP 413."""
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    get_settings.cache_clear()
    try:
        limit_bytes = 1 * 1024 * 1024
        payload = b"x" * (limit_bytes + 1)
        response = client.post(
            "/api/upload",
            files={"file": ("large.pdf", payload, "application/pdf")},
        )
        assert response.status_code == 413
        assert response.json() == {
            "detail": "File exceeds maximum allowed size of 1MB."
        }
    finally:
        get_settings.cache_clear()


def test_upload_valid_pdf_success() -> None:
    """Verify that a valid PDF returns HTTP 200 with accurate size and SHA-256 hash."""
    payload = make_valid_pdf_bytes("Valid test content for research paper")
    response = client.post(
        "/api/upload",
        files={"file": ("research_paper.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "research_paper.pdf"
    assert data["size_bytes"] == len(payload)
    assert data["doc_hash"] == hashlib.sha256(payload).hexdigest()
