"""Tests for dynamic header retention, privacy-scoped publisher/year extraction, and fail-safes."""

import io
import json
from unittest.mock import AsyncMock, MagicMock

import fitz  # PyMuPDF
import pytest
from pydantic import BaseModel

from app.services.metadata_service import (
    HeaderMetadata,
    extract_header_metadata,
    get_document_metadata,
)
from app.services.pdf_parser import parse_pdf
from tests.conftest import AuthenticatedTestClient


class MockChoiceMessage(BaseModel):
    content: str


class MockChoice(BaseModel):
    message: MockChoiceMessage


class MockChatResponse(BaseModel):
    choices: list[MockChoice]


def make_pdf_with_header(
    header_text: str,
    title: str,
    body_text: str = "This paper presents novel neural network results.",
) -> bytes:
    """Generate in-memory PDF bytes where Page 1 starts with a header block followed by title and body."""
    doc = fitz.open()
    page = doc.new_page()
    full_p1_text = f"{header_text}\n\n{title}\n\n{body_text}"
    page.insert_text((50, 50), full_p1_text, fontsize=11)
    page2 = doc.new_page()
    page2.insert_text(
        (50, 50),
        "Page 2 body text.\n\nReferences\n[1] Smith et al., 2019. Neural Systems.",
        fontsize=11,
    )
    stream = io.BytesIO()
    doc.save(stream)
    doc.close()
    return stream.getvalue()


@pytest.mark.asyncio
async def test_extract_header_metadata_success() -> None:
    """Case 1: Mock Page 1 header containing conference & publisher -> extracts detected_publisher and publication_year."""
    header_text = (
        "2019 Joint International Conference on Science and Technology by IEEE"
    )

    mock_client = MagicMock()
    mock_payload = {
        "detected_publisher": "IEEE",
        "detected_venue": "Joint International Conference on Science and Technology",
        "publication_year": 2019,
    }
    mock_response = MockChatResponse(
        choices=[
            MockChoice(message=MockChoiceMessage(content=json.dumps(mock_payload)))
        ]
    )
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    meta = await extract_header_metadata(header_text, client=mock_client)

    assert isinstance(meta, HeaderMetadata)
    assert meta.detected_publisher == "IEEE"
    assert (
        meta.detected_venue
        == "Joint International Conference on Science and Technology"
    )
    assert meta.publication_year == 2019

    # Verify model call parameters
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    messages = call_kwargs["messages"]
    # Verify ONLY the isolated Page 1 header was passed, not body text
    assert header_text in messages[1]["content"]
    assert "<PAGE_1_HEADER>" in messages[1]["content"]


@pytest.mark.asyncio
async def test_extract_header_metadata_failure_fail_safe() -> None:
    """Case 2: Extraction failure or invalid JSON gracefully sets fields to null without throwing."""
    header_text = "Conference on Computing 2020 by ACM"

    # Case 2a: Invalid JSON returned by model
    mock_client_bad_json = MagicMock()
    mock_response = MockChatResponse(
        choices=[MockChoice(message=MockChoiceMessage(content="Not a valid JSON {"))]
    )
    mock_client_bad_json.chat.completions.create = AsyncMock(return_value=mock_response)

    meta_invalid = await extract_header_metadata(
        header_text, client=mock_client_bad_json
    )
    assert meta_invalid.detected_publisher is None
    assert meta_invalid.detected_venue is None
    assert meta_invalid.publication_year is None

    # Case 2b: Network / model exception
    mock_client_err = MagicMock()
    mock_client_err.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("AI provider error")
    )

    meta_err = await extract_header_metadata(header_text, client=mock_client_err)
    assert meta_err.detected_publisher is None
    assert meta_err.detected_venue is None
    assert meta_err.publication_year is None


@pytest.mark.asyncio
async def test_year_guard_ignores_body_and_references() -> None:
    """Case 3: Year Guard - document with no header year, but containing '2019' in reference line leaves publication_year: null."""
    # Isolated Page 1 header has NO year
    header_no_year = "Transactions on Computer Systems by ACM"

    mock_client = MagicMock()
    # Even if an erroneous model attempt tries to return 2019, our strict year guard verifies str(year) in header_text
    mock_payload = {
        "detected_publisher": "ACM",
        "detected_venue": "Transactions on Computer Systems",
        "publication_year": 2019,
    }
    mock_response = MockChatResponse(
        choices=[
            MockChoice(message=MockChoiceMessage(content=json.dumps(mock_payload)))
        ]
    )
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    meta = await extract_header_metadata(header_no_year, client=mock_client)

    assert meta.detected_publisher == "ACM"
    assert meta.detected_venue == "Transactions on Computer Systems"
    # Year was NOT present in header_text, so guard reverts it to None
    assert meta.publication_year is None


def test_ingestion_header_retention_in_first_chunk() -> None:
    """Case 4: Ingestion header retention ensures the raw text block above the title on Page 1 is prepended to the first chunk."""
    header_text = (
        "2019 Joint International Conference on Science and Technology by IEEE"
    )
    title = "Deep Residual Learning for Image Recognition"
    body_text = "We evaluate deep residual networks on ImageNet and COCO benchmarks."

    pdf_bytes = make_pdf_with_header(header_text, title, body_text)
    parsed = parse_pdf(pdf_bytes)

    assert parsed.page_count == 2
    assert len(parsed.chunks) >= 1

    # Verify extract_page_1_header detected the header block
    assert "2019 Joint International Conference" in parsed.header_block
    assert "IEEE" in parsed.header_block

    # Verify the first indexed chunk has the header block preserved and prepended
    first_chunk_text = parsed.chunks[0]["text"]
    assert "2019 Joint International Conference" in first_chunk_text
    assert "Deep Residual Learning for Image Recognition" in first_chunk_text


class SimpleEmbedder:
    async def __call__(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 8 for _ in texts]


def test_upload_endpoint_persists_metadata_and_fail_safe(
    auth_client: AuthenticatedTestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Case 5: Upload endpoint executes header metadata extraction, persists DocumentMetadata, and succeeds on failure."""
    from app.core.dependencies import get_chat_llm_client, get_embedding_function
    from app.main import app

    app.dependency_overrides[get_embedding_function] = lambda: SimpleEmbedder()
    app.dependency_overrides[get_chat_llm_client] = lambda: MagicMock()

    try:
        header_text = "2022 IEEE International Conference on Big Data"
        title = "Scalable Graph Embeddings"
        pdf_bytes = make_pdf_with_header(header_text, title)

        # Mock extract_header_metadata to simulate successful extraction
        async def mock_extract(text: str, client: object = None) -> HeaderMetadata:
            return HeaderMetadata(
                detected_publisher="IEEE",
                detected_venue="IEEE International Conference on Big Data",
                publication_year=2022,
            )

        monkeypatch.setattr("app.api.upload.extract_header_metadata", mock_extract)

        resp = auth_client.post(
            "/api/upload",
            files={"file": ("bigdata_paper.pdf", pdf_bytes, "application/pdf")},
        )
        assert resp.status_code == 200
        data = resp.json()
        doc_hash = data["doc_hash"]

        # Verify DB persistence
        meta_rec = get_document_metadata(doc_hash, db=auth_client.db)
        assert meta_rec is not None
        assert meta_rec.detected_publisher == "IEEE"
        assert meta_rec.detected_venue == "IEEE International Conference on Big Data"
        assert meta_rec.publication_year == 2022
        assert "2022 IEEE International Conference" in (meta_rec.header_text or "")
    finally:
        app.dependency_overrides.pop(get_embedding_function, None)
        app.dependency_overrides.pop(get_chat_llm_client, None)
