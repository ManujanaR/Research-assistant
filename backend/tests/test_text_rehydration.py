import json
from pathlib import Path

import chromadb
import pytest

from app.core.config import get_settings
from app.core.dependencies import (
    get_chroma_client,
    get_embedding_function,
    get_llm_client,
    get_paper_text_store,
    get_summary_cache,
)
from app.main import app
from app.services.cache import SummaryCache
from app.services.qa import index_document, rebuild_text_from_chroma
from app.services.summary_service import InMemoryPaperTextStore
from tests.conftest import AuthenticatedTestClient
from tests.test_summarizer import VALID_SUMMARY_DICT, FakeOpenAIClient


class SimpleEmbedder:
    """Deterministic dummy embedder for tests."""

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]


@pytest.mark.asyncio
async def test_rehydration_after_restart(tmp_path: Path) -> None:
    """Index a document, create fresh text store (simulating restart), assert rebuilt text contains both pages."""
    chroma_dir = tmp_path / "test_chroma"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = SimpleEmbedder()

    doc_hash = "a" * 64
    chunks = [
        {"text": "Page 1: Deep learning representations.", "page": 1},
        {"text": "Page 2: Empirical evaluations on ImageNet.", "page": 2},
    ]

    await index_document(
        doc_hash=doc_hash,
        chunks=chunks,
        embed_fn=embedder,
        client=chroma_client,
    )

    # Simulate restart by creating a fresh text store instance with empty in-memory state
    fresh_store = InMemoryPaperTextStore(chroma_client=chroma_client)
    assert doc_hash not in fresh_store._store

    rebuilt_text = fresh_store.get_text(doc_hash)
    assert rebuilt_text is not None
    assert "Page 1: Deep learning representations." in rebuilt_text
    assert "Page 2: Empirical evaluations on ImageNet." in rebuilt_text

    # Verify chunk ordering is preserved
    p1_pos = rebuilt_text.index("Page 1:")
    p2_pos = rebuilt_text.index("Page 2:")
    assert p1_pos < p2_pos

    # Assert rebuilt text is now cached in memory
    assert doc_hash in fresh_store._store
    assert fresh_store._store[doc_hash] == rebuilt_text


def test_unknown_hash_returns_none(tmp_path: Path) -> None:
    """Unknown doc_hash returns None from fresh text store."""
    chroma_dir = tmp_path / "test_chroma"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))

    fresh_store = InMemoryPaperTextStore(chroma_client=chroma_client)
    unknown_hash = "b" * 64

    result = fresh_store.get_text(unknown_hash)
    assert result is None


def test_invalid_hash_raises_value_error(tmp_path: Path) -> None:
    """Invalid hash raises ValueError during rehydration lookup."""
    chroma_dir = tmp_path / "test_chroma"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))

    fresh_store = InMemoryPaperTextStore(chroma_client=chroma_client)
    with pytest.raises(ValueError):
        fresh_store.get_text("../etc/passwd")

    with pytest.raises(ValueError):
        rebuild_text_from_chroma("../etc/passwd", client=chroma_client)


@pytest.mark.asyncio
async def test_summary_endpoint_rehydration_after_restart(
    auth_client: AuthenticatedTestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate restart with empty in-memory store and summary cache miss; endpoint rehydrates text from Chroma."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-key")
    get_settings.cache_clear()

    chroma_dir = tmp_path / "chroma_endpoint"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = SimpleEmbedder()

    doc_hash = "c" * 64
    chunks = [
        {"text": "Page 1 text on optimization.", "page": 1},
        {"text": "Page 2 text on convergence bounds.", "page": 2},
    ]

    await index_document(
        doc_hash=doc_hash,
        chunks=chunks,
        embed_fn=embedder,
        client=chroma_client,
    )
    auth_client.record_ownership(doc_hash)

    # Empty summary cache
    cache_dir = tmp_path / "summary_cache"
    summary_cache = SummaryCache(cache_dir=cache_dir)

    # Fresh in-memory text store with Chroma fallback (simulating restart)
    restart_store = InMemoryPaperTextStore(chroma_client=chroma_client)
    fake_llm = FakeOpenAIClient([json.dumps(VALID_SUMMARY_DICT)])

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_summary_cache] = lambda: summary_cache
    app.dependency_overrides[get_paper_text_store] = lambda: restart_store
    app.dependency_overrides[get_llm_client] = lambda: fake_llm

    try:
        response = auth_client.post("/api/summary", json={"doc_hash": doc_hash})
        assert response.status_code == 200
        data = response.json()
        assert (
            data["header"]["title"]
            == VALID_SUMMARY_DICT["header"]["title"]
        )
        # Confirm that restart_store now has the text in memory
        assert doc_hash in restart_store._store
    finally:
        app.dependency_overrides.pop(get_chroma_client, None)
        app.dependency_overrides.pop(get_embedding_function, None)
        app.dependency_overrides.pop(get_summary_cache, None)
        app.dependency_overrides.pop(get_paper_text_store, None)
        app.dependency_overrides.pop(get_llm_client, None)
