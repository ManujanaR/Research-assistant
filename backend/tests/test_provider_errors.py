import io
import json
import logging
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import chromadb
import httpx
import openai
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.config import BACKEND_DIR, Settings
from app.core.dependencies import (
    get_chroma_client,
    get_embedding_function,
    get_llm_client,
    get_paper_text_store,
    get_summary_cache,
)
from app.main import app
from app.services.cache import SummaryCache
from app.services.qa import (
    EmbeddingDimensionMismatchError,
    index_document,
    retrieve,
    stream_chat_response,
)
from app.services.summary_service import InMemoryPaperTextStore

client = TestClient(app)

SAMPLE_SUMMARY = {
    "title_authors_abstract": "Title - Authors - Abstract",
    "problem_statement": "Problem Statement",
    "methodology": "Methodology",
    "key_results": "Key Results",
    "conclusion": "Conclusion",
}


def make_valid_pdf_bytes() -> bytes:
    """Create a minimal valid two-page PDF with text."""
    doc = pymupdf.open()
    page1 = doc.new_page()
    page1.insert_text((50, 50), "Page 1: Sample academic introduction.")
    page2 = doc.new_page()
    page2.insert_text((50, 50), "Page 2: Results and experimental methodology.")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


class DimensionEmbedder:
    """Embedder returning vectors of a configurable dimension."""

    def __init__(self, dim: int = 8) -> None:
        self.dim = dim
        self.call_count = 0

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        embeddings: list[list[float]] = []
        for _ in texts:
            vec = [0.1] * self.dim
            embeddings.append(vec)
        return embeddings


@pytest.mark.asyncio
async def test_collection_rebuild_on_embedding_model_change(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Collection built with model A is deleted and rebuilt when model changes to model B with WARNING logged."""
    chroma_client = chromadb.PersistentClient(path=str(tmp_path / ".chroma"))
    doc_hash = "a" * 64
    chunks = [{"text": "Sample text chunk", "page": 1}]
    embedder = DimensionEmbedder(dim=8)

    settings_a = Settings(
        EMBEDDING_MODEL="model-A",
        CHROMA_DIR=str(tmp_path / ".chroma"),
        _env_file=None,
    )
    with patch("app.services.qa.get_settings", return_value=settings_a):
        await index_document(doc_hash, chunks, embedder, client=chroma_client)

    collection_name = "doc_" + doc_hash[:32]
    coll = chroma_client.get_collection(collection_name)
    assert coll.metadata["embedding_model"] == "model-A"
    assert coll.metadata["embedding_dim"] == 8
    assert embedder.call_count == 1

    # Now change embedding model to model-B
    settings_b = Settings(
        EMBEDDING_MODEL="model-B",
        CHROMA_DIR=str(tmp_path / ".chroma"),
        _env_file=None,
    )
    with (
        patch("app.services.qa.get_settings", return_value=settings_b),
        caplog.at_level(logging.WARNING),
    ):
        await index_document(doc_hash, chunks, embedder, client=chroma_client)

    assert embedder.call_count == 2
    coll_rebuilt = chroma_client.get_collection(collection_name)
    assert coll_rebuilt.metadata["embedding_model"] == "model-B"
    assert any(
        "rebuilt because the embedding model changed" in rec.message
        for rec in caplog.records
    )


@pytest.mark.asyncio
async def test_mismatched_embedding_dimension_raises_clear_error_and_returns_409(
    tmp_path: Path,
) -> None:
    """Query with mismatched embedding dimension raises EmbeddingDimensionMismatchError and /api/chat returns 409."""
    chroma_client = chromadb.PersistentClient(path=str(tmp_path / ".chroma"))
    doc_hash = "b" * 64
    chunks = [{"text": "Stored chunk with dim 8", "page": 1}]
    doc_embedder = DimensionEmbedder(dim=8)

    settings = Settings(
        EMBEDDING_MODEL="test-embed-model",
        CHROMA_DIR=str(tmp_path / ".chroma"),
        _env_file=None,
    )
    with patch("app.services.qa.get_settings", return_value=settings):
        await index_document(doc_hash, chunks, doc_embedder, client=chroma_client)

    query_embedder_16 = DimensionEmbedder(dim=16)

    # Unit test: retrieve directly raises clear error
    with pytest.raises(EmbeddingDimensionMismatchError) as exc_info:
        await retrieve(
            doc_hash,
            "test query",
            query_embedder_16,
            client=chroma_client,
        )
    assert (
        "Query embedding dimension (16) does not match collection embedding dimension (8)"
        in str(exc_info.value)
    )

    # Endpoint test: /api/chat maps to 409
    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: query_embedder_16
    try:
        response = client.post(
            "/api/chat",
            json={"doc_hash": doc_hash, "message": "test query"},
        )
        assert response.status_code == 409
        assert (
            response.json()["detail"]
            == "The document index was built with a different embedding model. Re-upload the paper to rebuild it."
        )
    finally:
        app.dependency_overrides.clear()


def test_summary_cache_miss_on_model_name_change_calls_llm(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Summary cache entry with a different model_name is a miss and LLM is called again."""
    cache = SummaryCache(cache_dir=tmp_path)
    text_store = InMemoryPaperTextStore()
    doc_hash = "c" * 64
    text_store.set_text(doc_hash, "Full paper text content.")

    # Store entry under model-A
    cache.set(doc_hash, SAMPLE_SUMMARY, model_name="model-A")

    # Set configured model to model-B
    settings_b = Settings(
        OPENAI_API_KEY="sk-mock-key",
        MODEL_NAME="model-B",
        SUMMARY_CACHE_DIR=str(tmp_path),
        _env_file=None,
    )

    llm_call_count = 0

    class FakeResponse:
        def __init__(self) -> None:
            self.choices = [
                MagicMock(message=MagicMock(content=json.dumps(SAMPLE_SUMMARY)))
            ]

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(*args: Any, **kwargs: Any) -> FakeResponse:
                    nonlocal llm_call_count
                    llm_call_count += 1
                    return FakeResponse()

    app.dependency_overrides[get_summary_cache] = lambda: cache
    app.dependency_overrides[get_paper_text_store] = lambda: text_store
    app.dependency_overrides[get_llm_client] = lambda: FakeClient()

    try:
        with (
            patch("app.api.summary.get_settings", return_value=settings_b),
            patch("app.services.cache.get_settings", return_value=settings_b),
            caplog.at_level(logging.WARNING),
        ):
            response = client.post("/api/summary", json={"doc_hash": doc_hash})
            assert response.status_code == 200
            assert llm_call_count == 1
            assert any(
                "cached model 'model-A' differs from configured model 'model-B'"
                in rec.message
                for rec in caplog.records
            )
    finally:
        app.dependency_overrides.clear()


def test_api_status_error_on_summary_returns_502(tmp_path: Path) -> None:
    """APIStatusError with status 404 on /api/summary returns 502 with status code in detail and no response body."""
    cache = SummaryCache(cache_dir=tmp_path)
    text_store = InMemoryPaperTextStore()
    doc_hash = "d" * 64
    text_store.set_text(doc_hash, "Paper text.")

    secret_payload = '{"secret": "internal_error_should_not_leak"}'
    fake_response = httpx.Response(
        404,
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
        text=secret_payload,
    )
    status_error = openai.APIStatusError(
        "Not Found", response=fake_response, body={"secret": "internal_error"}
    )

    class FailingClient:
        class chat:
            class completions:
                @staticmethod
                async def create(*args: Any, **kwargs: Any) -> Any:
                    raise status_error

    app.dependency_overrides[get_summary_cache] = lambda: cache
    app.dependency_overrides[get_paper_text_store] = lambda: text_store
    app.dependency_overrides[get_llm_client] = lambda: FailingClient()

    settings = Settings(
        OPENAI_API_KEY="sk-mock-key",
        SUMMARY_CACHE_DIR=str(tmp_path),
        _env_file=None,
    )

    try:
        with (
            patch("app.api.summary.get_settings", return_value=settings),
            patch("app.services.cache.get_settings", return_value=settings),
        ):
            response = client.post("/api/summary", json={"doc_hash": doc_hash})
            assert response.status_code == 502
            assert (
                response.json()["detail"]
                == "The AI provider returned an error (status 404). Check MODEL_NAME and EMBEDDING_MODEL in backend/.env."
            )
            assert "internal_error_should_not_leak" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_api_status_error_on_upload_returns_502() -> None:
    """APIStatusError on /api/upload during embedding returns 502 with status code in detail and no response body."""
    secret_payload = '{"secret": "embedding_failure_leak"}'
    fake_response = httpx.Response(
        404,
        request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"),
        text=secret_payload,
    )
    status_error = openai.APIStatusError(
        "Model Not Found", response=fake_response, body={"secret": "internal"}
    )

    async def failing_embed_fn(texts: list[str]) -> list[list[float]]:
        raise status_error

    pdf_bytes = make_valid_pdf_bytes()
    app.dependency_overrides[get_embedding_function] = lambda: failing_embed_fn

    try:
        response = client.post(
            "/api/upload",
            files={"file": ("paper.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
        )
        assert response.status_code == 502
        assert (
            response.json()["detail"]
            == "The AI provider returned an error (status 404). Check MODEL_NAME and EMBEDDING_MODEL in backend/.env."
        )
        assert "embedding_failure_leak" not in response.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_midstream_api_status_error_emits_error_and_no_done() -> None:
    """Mid-stream APIStatusError during chat streaming emits error event and no done event."""
    fake_response = httpx.Response(
        500,
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
        text="Internal Server Error",
    )
    status_error = openai.APIStatusError(
        "Internal Error", response=fake_response, body=None
    )

    async def mock_stream_generator() -> AsyncIterator[Any]:
        yield MagicMock(choices=[MagicMock(delta=MagicMock(content="First token"))])
        raise status_error

    class MockStreamClient:
        class chat:
            class completions:
                @staticmethod
                async def create(*args: Any, **kwargs: Any) -> Any:
                    return mock_stream_generator()

    client_mock = MockStreamClient()
    events: list[str] = []
    async for chunk in stream_chat_response([], [], client_mock):
        events.append(chunk)

    joined = "".join(events)
    assert "event: error" in joined
    assert (
        "The AI provider returned an error (status 500). Check MODEL_NAME and EMBEDDING_MODEL in backend/.env."
        in joined
    )
    assert "event: done" not in joined


def test_resolved_data_paths_are_absolute_and_independent_of_cwd(
    tmp_path: Path,
) -> None:
    """Resolved CHROMA_DIR and SUMMARY_CACHE_DIR are absolute and independent of current working directory."""
    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        settings = Settings(_env_file=None)

        assert os.path.isabs(settings.chroma_dir)
        assert settings.chroma_dir.endswith(".chroma")
        assert str(BACKEND_DIR) in settings.chroma_dir

        assert os.path.isabs(settings.summary_cache_dir)
        assert settings.summary_cache_dir.endswith(".cache/summaries")
        assert str(BACKEND_DIR) in settings.summary_cache_dir
    finally:
        os.chdir(old_cwd)
