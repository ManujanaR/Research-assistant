import hashlib

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app

client = TestClient(app)


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
    payload = b"%PDF-1.4 test"
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
    payload = b"%PDF-1.4 valid test content"
    response = client.post(
        "/api/upload",
        files={"file": ("research_paper.pdf", payload, "application/pdf")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "research_paper.pdf"
    assert data["size_bytes"] == len(payload)
    assert data["doc_hash"] == hashlib.sha256(payload).hexdigest()
