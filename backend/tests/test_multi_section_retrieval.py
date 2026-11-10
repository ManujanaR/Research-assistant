"""Unit and integration tests for dual-pass multi-section retrieval."""

import asyncio
from pathlib import Path
from typing import Any

import chromadb
import pytest

from app.core.dependencies import (
    get_chat_llm_client,
    get_chroma_client,
    get_embedding_function,
)
from app.main import app
from app.schemas.chat import ChatMessage
from app.services.classifier import ClassifierResult
from app.services.qa import (
    FALLBACK_GROUNDING_MESSAGE,
    RetrievedChunk,
    index_document,
    retrieve_multi_section,
)
from tests.test_chat_endpoint import (
    AuthenticatedTestClient,
    FakeChatClient,
    FakeChatStream,
    SimpleCountingEmbedder,
    parse_sse_events,
)


@pytest.mark.asyncio
async def test_retrieve_multi_section_executes_dual_passes_and_deduplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multi-section retrieval executes dual passes with target_top_k=3, deduplicates by ID, and sorts by distance."""
    recorded_queries: list[str] = []
    recorded_top_ks: list[int] = []

    async def fake_retrieve(
        doc_hash: str,
        query: str,
        embed_fn: Any,
        top_k: int = 5,
        client: Any = None,
    ) -> list[RetrievedChunk]:
        recorded_queries.append(query)
        recorded_top_ks.append(top_k)
        if "abstract" in query.lower():
            return [
                RetrievedChunk(id="c1", text="Abstract chunk 1", page=1, distance=0.65),
                RetrievedChunk(
                    id="c_shared", text="Shared chunk", page=1, distance=0.72
                ),
                RetrievedChunk(id="c2", text="Abstract chunk 2", page=1, distance=0.78),
            ]
        else:
            return [
                RetrievedChunk(id="c3", text="Results chunk 3", page=3, distance=0.55),
                RetrievedChunk(
                    id="c_shared", text="Shared chunk duplicate", page=1, distance=0.70
                ),
                RetrievedChunk(id="c4", text="Results chunk 4", page=3, distance=0.82),
            ]

    monkeypatch.setattr("app.services.qa.retrieve", fake_retrieve)

    embedder = SimpleCountingEmbedder()
    merged = await retrieve_multi_section(
        doc_hash="1" * 64,
        embed_fn=embedder,
        comparison_targets=["abstract", "results"],
        target_top_k=3,
    )

    # Verify two passes were made with top_k=3
    assert len(recorded_queries) == 2
    assert recorded_top_ks == [3, 3]
    assert "abstract" in recorded_queries[0].lower()
    assert "results" in recorded_queries[1].lower()

    # Verify deduplication: 6 items returned -> 5 unique chunks
    assert len(merged) == 5
    chunk_ids = [c.id for c in merged]
    assert chunk_ids.count("c_shared") == 1

    # Verify sorting by distance in ascending order
    distances = [c.distance for c in merged]
    assert distances == sorted(distances)
    assert merged[0].id == "c3"  # distance 0.55
    assert merged[1].id == "c1"  # distance 0.65


@pytest.mark.asyncio
async def test_retrieve_multi_section_defaults_when_targets_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When comparison_targets is omitted or empty, it defaults to abstract and results passes."""
    recorded_queries: list[str] = []

    async def fake_retrieve(
        doc_hash: str,
        query: str,
        embed_fn: Any,
        top_k: int = 5,
        client: Any = None,
    ) -> list[RetrievedChunk]:
        recorded_queries.append(query)
        return []

    monkeypatch.setattr("app.services.qa.retrieve", fake_retrieve)

    embedder = SimpleCountingEmbedder()
    merged = await retrieve_multi_section(
        doc_hash="1" * 64,
        embed_fn=embedder,
        comparison_targets=[],
    )

    assert len(recorded_queries) == 2
    assert "abstract" in recorded_queries[0].lower()
    assert "results" in recorded_queries[1].lower()
    assert merged == []


@pytest.mark.asyncio
async def test_retrieve_multi_section_single_target_resolves_complementary_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When comparison_targets contains only one target, it adds the complementary section."""
    recorded_queries: list[str] = []

    async def fake_retrieve(
        doc_hash: str,
        query: str,
        embed_fn: Any,
        top_k: int = 5,
        client: Any = None,
    ) -> list[RetrievedChunk]:
        recorded_queries.append(query)
        return []

    monkeypatch.setattr("app.services.qa.retrieve", fake_retrieve)

    embedder = SimpleCountingEmbedder()
    await retrieve_multi_section(
        doc_hash="1" * 64,
        embed_fn=embedder,
        comparison_targets=["abstract"],
    )

    assert len(recorded_queries) == 2
    assert "abstract" in recorded_queries[0].lower()
    assert "results" in recorded_queries[1].lower()


def test_chat_endpoint_comparative_triggers_multi_section_retrieval(
    auth_client: AuthenticatedTestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Comparative query routes to retrieve_multi_section and preserves up to 6 cross-section chunks."""
    doc_hash = "2" * 64
    chroma_dir = tmp_path / "chroma_test_multi"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = SimpleCountingEmbedder()

    # Index document with 4 chunks
    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[
                {"text": "Abstract: Study on geohelminths.", "page": 1},
                {"text": "Results: Observed 40% reduction in prevalence.", "page": 3},
                {"text": "Results: Statistically significant decline.", "page": 3},
                {"text": "Conclusion: Treatment is effective.", "page": 4},
            ],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    # Mock classifier to return comparative intent
    async def fake_classify(*args: Any, **kwargs: Any) -> ClassifierResult:
        return ClassifierResult(
            intent="document_question",
            query="compare abstract and results",
            is_comparative=True,
            comparison_targets=["abstract", "results"],
        )

    monkeypatch.setattr("app.api.chat.classify_and_rewrite", fake_classify)

    passed_chunks: list[RetrievedChunk] = []

    def fake_assemble_chat_messages(
        question: str,
        history: list[ChatMessage],
        chunks: list[RetrievedChunk] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        nonlocal passed_chunks
        passed_chunks = chunks or []
        return [
            {"role": "system", "content": "system"},
            {"role": "user", "content": question},
        ]

    monkeypatch.setattr(
        "app.api.chat.assemble_chat_messages", fake_assemble_chat_messages
    )

    fake_client = FakeChatClient(
        stream_factory=lambda **_: FakeChatStream(
            tokens=["Comparative", " answer", "."]
        )
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    response = auth_client.post(
        "/api/chat",
        json={
            "doc_hash": doc_hash,
            "message": "Does the abstract accurately summarize the results?",
        },
    )
    assert response.status_code == 200

    # Passed chunks should contain chunks from both sections
    assert len(passed_chunks) >= 2
    pages = {c.page for c in passed_chunks}
    assert 1 in pages  # Abstract on page 1
    assert 3 in pages  # Results on page 3


def test_chat_endpoint_non_comparative_triggers_single_retrieval(
    auth_client: AuthenticatedTestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-comparative query routes to single retrieve call and caps at 3 chunks."""
    doc_hash = "3" * 64
    chroma_dir = tmp_path / "chroma_test_single"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = SimpleCountingEmbedder()

    # Index document with 5 chunks
    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[
                {"text": "Chunk 1", "page": 1},
                {"text": "Chunk 2", "page": 2},
                {"text": "Chunk 3", "page": 3},
                {"text": "Chunk 4", "page": 4},
                {"text": "Chunk 5", "page": 5},
            ],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    # Mock classifier to return non-comparative intent
    async def fake_classify(*args: Any, **kwargs: Any) -> ClassifierResult:
        return ClassifierResult(
            intent="document_question",
            query="summarize methodology",
            is_comparative=False,
            comparison_targets=[],
        )

    monkeypatch.setattr("app.api.chat.classify_and_rewrite", fake_classify)

    multi_section_called = False

    async def fake_multi_section(*args: Any, **kwargs: Any) -> list[RetrievedChunk]:
        nonlocal multi_section_called
        multi_section_called = True
        return []

    monkeypatch.setattr("app.api.chat.retrieve_multi_section", fake_multi_section)

    passed_chunks: list[RetrievedChunk] = []

    def fake_assemble_chat_messages(
        question: str,
        history: list[ChatMessage],
        chunks: list[RetrievedChunk] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[dict[str, str]]:
        nonlocal passed_chunks
        passed_chunks = chunks or []
        return [
            {"role": "system", "content": "system"},
            {"role": "user", "content": question},
        ]

    monkeypatch.setattr(
        "app.api.chat.assemble_chat_messages", fake_assemble_chat_messages
    )

    fake_client = FakeChatClient(
        stream_factory=lambda **_: FakeChatStream(
            tokens=["Methodology", " summary", "."]
        )
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    response = auth_client.post(
        "/api/chat",
        json={
            "doc_hash": doc_hash,
            "message": "Summarize the methodology used in this paper.",
        },
    )
    assert response.status_code == 200
    assert not multi_section_called
    assert len(passed_chunks) <= 3


def test_missing_section_yields_fallback_without_substituting_arbitrary_text(
    auth_client: AuthenticatedTestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a targeted section has no matching chunks below distance cutoff, no arbitrary text is substituted."""
    doc_hash = "4" * 64
    chroma_dir = tmp_path / "chroma_test_missing"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = SimpleCountingEmbedder()

    # Index document with 0 relevant chunks
    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[{"text": "Irrelevant chunk text.", "page": 1}],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    async def fake_classify(*args: Any, **kwargs: Any) -> ClassifierResult:
        return ClassifierResult(
            intent="document_question",
            query="compare abstract and results",
            is_comparative=True,
            comparison_targets=["abstract", "results"],
        )

    monkeypatch.setattr("app.api.chat.classify_and_rewrite", fake_classify)

    # Return chunks above distance threshold
    async def fake_multi_section(*args: Any, **kwargs: Any) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(id="c1", text="High distance chunk", page=1, distance=0.95)
        ]

    monkeypatch.setattr("app.api.chat.retrieve_multi_section", fake_multi_section)

    fake_client = FakeChatClient(
        stream_factory=lambda **_: FakeChatStream(tokens=[FALLBACK_GROUNDING_MESSAGE])
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    response = auth_client.post(
        "/api/chat",
        json={
            "doc_hash": doc_hash,
            "message": "Does the abstract accurately summarize the results?",
        },
    )
    assert response.status_code == 200
    events = parse_sse_events(response.text)
    token_texts = [e["data"]["text"] for e in events if e["event"] == "token"]
    streamed_full_answer = "".join(token_texts)
    assert streamed_full_answer == FALLBACK_GROUNDING_MESSAGE
    sources_events = [e for e in events if e["event"] == "sources"]
    assert len(sources_events) == 1
    assert sources_events[0]["data"] == []
