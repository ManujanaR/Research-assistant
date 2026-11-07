import json
import os
import tempfile
from pathlib import Path
from typing import Any

import chromadb
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.dependencies import (
    get_chroma_client,
    get_embedding_function,
    get_llm_client,
    get_paper_text_store,
)
from app.main import app
from app.services.qa import (
    get_chroma_collection_name,
    index_document,
    retrieve,
)
from tests.test_summarizer import VALID_SUMMARY_DICT, FakeOpenAIClient


def make_two_page_pdf_bytes() -> bytes:
    """Create a two-page PDF with distinct text on each page."""
    doc = pymupdf.open()
    page1 = doc.new_page()
    page1.insert_text(
        (50, 50),
        "Page 1: Introduction to artificial intelligence and deep neural networks.",
    )
    page2 = doc.new_page()
    page2.insert_text(
        (50, 50),
        "Page 2: Methodology for reinforcement learning and policy gradient algorithms.",
    )
    data = doc.tobytes()
    doc.close()
    return data


class CountingEmbedder:
    """Deterministic embedding function tracking call counts for tests."""

    def __init__(self, dim: int = 8) -> None:
        self.call_count = 0
        self.dim = dim

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        embeddings: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            lower = text.lower()
            if "page 1" in lower or "introduction" in lower:
                vec[0] = 1.0
            if "page 2" in lower or "methodology" in lower or "reinforcement" in lower:
                vec[1] = 1.0
            # Ensure non-zero vector
            if sum(vec) == 0:
                vec[2] = 1.0
            embeddings.append(vec)
        return embeddings


@pytest.fixture
def chroma_test_client(tmp_path: Path) -> chromadb.ClientAPI:
    """Create an isolated persistent Chroma client inside pytest tmp_path."""
    return chromadb.PersistentClient(path=str(tmp_path / ".chroma"))


@pytest.mark.asyncio
async def test_indexing_creates_collection_with_page_metadata(
    chroma_test_client: chromadb.ClientAPI,
) -> None:
    """Verify that indexing creates collection doc_<first 32 hex chars> with metadata pages 1 and 2."""
    doc_hash = "a" * 64
    chunks = [
        {"text": "Paragraph from page 1", "page": 1},
        {"text": "Paragraph from page 2", "page": 2},
    ]
    embedder = CountingEmbedder()

    await index_document(doc_hash, chunks, embedder, client=chroma_test_client)

    expected_name = "doc_" + ("a" * 32)
    collection = chroma_test_client.get_collection(name=expected_name)
    assert collection.count() == 2

    stored = collection.get()
    pages = [m["page"] for m in stored["metadatas"]]
    assert 1 in pages
    assert 2 in pages


@pytest.mark.asyncio
async def test_reindexing_same_document_skips_embedding(
    chroma_test_client: chromadb.ClientAPI,
) -> None:
    """Verify that re-indexing an already complete collection skips calling the embed function."""
    doc_hash = "b" * 64
    chunks = [
        {"text": "Sample chunk 1", "page": 1},
        {"text": "Sample chunk 2", "page": 2},
    ]
    embedder = CountingEmbedder()

    # First indexing call
    await index_document(doc_hash, chunks, embedder, client=chroma_test_client)
    assert embedder.call_count == 1

    # Second indexing call on identical collection
    await index_document(doc_hash, chunks, embedder, client=chroma_test_client)
    assert embedder.call_count == 1, (
        "Embed function should not be called when collection is complete"
    )


@pytest.mark.asyncio
async def test_retrieve_matching_page_returns_correct_page_metadata(
    chroma_test_client: chromadb.ClientAPI,
) -> None:
    """Verify that query matching page 2 text returns a chunk with page == 2."""
    doc_hash = "c" * 64
    chunks = [
        {"text": "Page 1: Introduction to computer science", "page": 1},
        {
            "text": "Page 2: Methodology for reinforcement learning algorithms",
            "page": 2,
        },
    ]
    embedder = CountingEmbedder()
    await index_document(doc_hash, chunks, embedder, client=chroma_test_client)

    results = await retrieve(
        doc_hash,
        "Methodology for reinforcement learning",
        embedder,
        top_k=1,
        client=chroma_test_client,
    )
    assert len(results) == 1
    assert results[0].page == 2
    assert "Page 2" in results[0].text


@pytest.mark.asyncio
async def test_retrieve_top_k_larger_than_chunk_count(
    chroma_test_client: chromadb.ClientAPI,
) -> None:
    """Verify that top_k larger than stored count returns all chunks without error."""
    doc_hash = "d" * 64
    chunks = [
        {"text": "Sole chunk in doc", "page": 1},
    ]
    embedder = CountingEmbedder()
    await index_document(doc_hash, chunks, embedder, client=chroma_test_client)

    results = await retrieve(
        doc_hash,
        "Sole chunk",
        embedder,
        top_k=10,
        client=chroma_test_client,
    )
    assert len(results) == 1
    assert results[0].page == 1


@pytest.mark.asyncio
async def test_invalid_hash_raises_value_error(
    chroma_test_client: chromadb.ClientAPI,
) -> None:
    """Verify that non-64 hex hashes raise ValueError in both index and retrieve."""
    embedder = CountingEmbedder()

    with pytest.raises(ValueError):
        await index_document(
            "invalid_hash",
            [{"text": "t", "page": 1}],
            embedder,
            client=chroma_test_client,
        )

    with pytest.raises(ValueError):
        await retrieve("invalid_hash", "query", embedder, client=chroma_test_client)

    with pytest.raises(ValueError):
        get_chroma_collection_name("../etc/passwd")


@pytest.mark.asyncio
async def test_zero_chunk_document_raises_and_creates_no_collection(
    chroma_test_client: chromadb.ClientAPI,
) -> None:
    """Verify that indexing an empty chunk list raises ValueError and creates no collection."""
    doc_hash = "e" * 64
    embedder = CountingEmbedder()

    with pytest.raises(ValueError, match="zero chunks"):
        await index_document(doc_hash, [], embedder, client=chroma_test_client)

    expected_name = "doc_" + ("e" * 32)
    with pytest.raises((chromadb.errors.ChromaError, ValueError, KeyError)):
        chroma_test_client.get_collection(name=expected_name)


def test_upload_to_summary_integration_with_shared_text_store(
    auth_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Integration test: upload a 2-page PDF and call /api/summary with NO stubbed text store."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-key")
    get_settings.cache_clear()

    # Use isolated test chroma client and fake embedder/LLM
    test_chroma = chromadb.PersistentClient(path=str(tmp_path / ".chroma"))
    embedder = CountingEmbedder()
    fake_llm = FakeOpenAIClient([json.dumps(VALID_SUMMARY_DICT)])

    # Clear paper text store before test to ensure clean state
    get_paper_text_store().clear()

    # Override ONLY the LLM client, Chroma client, and embedder (leave text store untouched!)
    app.dependency_overrides[get_chroma_client] = lambda: test_chroma
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_llm_client] = lambda: fake_llm

    try:
        # Step 1: Upload 2-page PDF
        pdf_bytes = make_two_page_pdf_bytes()
        upload_resp = auth_client.post(
            "/api/upload",
            files={"file": ("integration_paper.pdf", pdf_bytes, "application/pdf")},
        )
        assert upload_resp.status_code == 200
        upload_data = upload_resp.json()
        doc_hash = upload_data["doc_hash"]
        assert upload_data["page_count"] == 2
        assert upload_data["chunk_count"] >= 2

        # Step 2: Request summary with real text store
        summary_resp = auth_client.post("/api/summary", json={"doc_hash": doc_hash})
        assert summary_resp.status_code == 200
        assert summary_resp.json() == VALID_SUMMARY_DICT
        assert len(fake_llm.chat.completions.calls) == 1
    finally:
        app.dependency_overrides.pop(get_chroma_client, None)
        app.dependency_overrides.pop(get_embedding_function, None)
        app.dependency_overrides.pop(get_llm_client, None)
        get_settings.cache_clear()


def test_temp_file_deleted_when_parser_raises(
    auth_client: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that temporary PDF file is deleted in finally block even when parsing raises."""
    test_chroma = chromadb.PersistentClient(path=str(tmp_path / ".chroma"))
    embedder = CountingEmbedder()

    app.dependency_overrides[get_chroma_client] = lambda: test_chroma
    app.dependency_overrides[get_embedding_function] = lambda: embedder

    created_temp_paths: list[str] = []
    orig_named_temp = tempfile.NamedTemporaryFile

    def recording_named_temp(*args: Any, **kwargs: Any) -> Any:
        tf = orig_named_temp(*args, **kwargs)
        created_temp_paths.append(tf.name)
        return tf

    monkeypatch.setattr(
        "app.api.upload.tempfile.NamedTemporaryFile", recording_named_temp
    )
    monkeypatch.setattr(
        "app.api.upload.parse_pdf",
        lambda _: (_ for _ in ()).throw(RuntimeError("Forced parser crash")),
    )

    try:
        pdf_bytes = make_two_page_pdf_bytes()
        with pytest.raises(RuntimeError, match="Forced parser crash"):
            auth_client.post(
                "/api/upload",
                files={"file": ("crash.pdf", pdf_bytes, "application/pdf")},
            )

        assert len(created_temp_paths) == 1
        assert not os.path.exists(created_temp_paths[0]), (
            "Temp PDF file must be deleted in finally block"
        )
    finally:
        app.dependency_overrides.pop(get_chroma_client, None)
        app.dependency_overrides.pop(get_embedding_function, None)


def test_upload_sample_scanned_pdf_returns_422(
    auth_client: TestClient, tmp_path: Path
) -> None:
    """Verify that uploading sample_scanned.pdf returns HTTP 422 with exact parser error message."""
    test_chroma = chromadb.PersistentClient(path=str(tmp_path / ".chroma"))
    embedder = CountingEmbedder()

    app.dependency_overrides[get_chroma_client] = lambda: test_chroma
    app.dependency_overrides[get_embedding_function] = lambda: embedder

    try:
        scanned_path = Path(__file__).parent / "fixtures" / "sample_scanned.pdf"
        assert scanned_path.is_file()

        response = auth_client.post(
            "/api/upload",
            files={
                "file": (
                    "sample_scanned.pdf",
                    scanned_path.read_bytes(),
                    "application/pdf",
                )
            },
        )
        assert response.status_code == 422
        assert response.json() == {
            "detail": "The uploaded PDF contains no extractable text. Scanned documents or image-only PDFs are not supported."
        }
    finally:
        app.dependency_overrides.pop(get_chroma_client, None)
        app.dependency_overrides.pop(get_embedding_function, None)


def test_upload_corrupt_bytes_returns_400(
    auth_client: TestClient, tmp_path: Path
) -> None:
    """Verify that uploading corrupt bytes with application/pdf returns HTTP 400."""
    test_chroma = chromadb.PersistentClient(path=str(tmp_path / ".chroma"))
    embedder = CountingEmbedder()

    app.dependency_overrides[get_chroma_client] = lambda: test_chroma
    app.dependency_overrides[get_embedding_function] = lambda: embedder

    try:
        response = auth_client.post(
            "/api/upload",
            files={"file": ("corrupt.pdf", b"not a valid pdf", "application/pdf")},
        )
        assert response.status_code == 400
        assert response.json() == {
            "detail": "The uploaded file could not be parsed as a PDF."
        }
    finally:
        app.dependency_overrides.pop(get_chroma_client, None)
        app.dependency_overrides.pop(get_embedding_function, None)
