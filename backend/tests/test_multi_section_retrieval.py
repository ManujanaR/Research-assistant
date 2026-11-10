"""Unit and integration tests for multi-section retrieval."""

from pathlib import Path
from typing import Any

import chromadb
import pytest
from app.services.qa import (
    RetrievedChunk,
    index_document,
    retrieve_multi_section,
)


class SectionEmbedder:
    """Deterministic section-aware embedder for multi-section retrieval tests."""

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for text in texts:
            vec = [0.0, 0.0, 0.0, 0.0]
            lower = text.lower()
            if "abstract" in lower:
                vec[0] = 1.0
            if "result" in lower:
                vec[1] = 1.0
            if "method" in lower:
                vec[2] = 1.0
            if not any(vec):
                vec[3] = 1.0
            embeddings.append(vec)
        return embeddings


@pytest.mark.asyncio
async def test_dual_target_retrieval_yields_both_sections(tmp_path: Path) -> None:
    """Dual-target retrieval yields chunks for both requested sections."""
    doc_hash = "a" * 64
    chroma_client = chromadb.PersistentClient(path=str(tmp_path / "chroma_dual"))
    embedder = SectionEmbedder()

    chunks = [
        {"text": "Abstract: Comprehensive overview of methods and goals.", "page": 1},
        {"text": "Results: Observed 40% reduction in error rates.", "page": 3},
        {"text": "Discussion: Implications of our findings.", "page": 4},
    ]
    await index_document(
        doc_hash=doc_hash,
        chunks=chunks,
        embed_fn=embedder,
        client=chroma_client,
    )

    results = await retrieve_multi_section(
        doc_hash=doc_hash,
        targets=["abstract", "results"],
        embed_fn=embedder,
        client=chroma_client,
        top_k=2,
    )

    assert len(results) >= 2
    pages = {c.page for c in results}
    assert 1 in pages
    assert 3 in pages

    # Verify order is sorted by distance ascending
    distances = [c.distance for c in results]
    assert distances == sorted(distances)


@pytest.mark.asyncio
async def test_deduplication_of_overlapping_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Overlapping chunks returned across multiple passes are deduplicated by chunk ID."""
    recorded_queries: list[str] = []

    async def fake_retrieve(
        doc_hash: str,
        query: str,
        embed_fn: Any,
        top_k: int = 5,
        client: Any = None,
    ) -> list[RetrievedChunk]:
        recorded_queries.append(query)
        if "Abstract" in query or "abstract" in query:
            return [
                RetrievedChunk(id="c1", text="Abstract chunk 1", page=1, distance=0.1),
                RetrievedChunk(
                    id="c_shared", text="Shared chunk", page=1, distance=0.4
                ),
            ]
        elif "Results" in query or "results" in query:
            return [
                RetrievedChunk(
                    id="c_shared", text="Shared chunk duplicate", page=1, distance=0.3
                ),
                RetrievedChunk(id="c2", text="Results chunk 2", page=3, distance=0.2),
            ]
        return []

    monkeypatch.setattr("app.services.qa.retrieve", fake_retrieve)

    embedder = SectionEmbedder()
    results = await retrieve_multi_section(
        doc_hash="b" * 64,
        targets=["abstract", "results"],
        embed_fn=embedder,
        top_k=2,
    )

    assert recorded_queries == [
        "Abstract background objective methods results conclusion",
        "Results findings data analysis outcomes",
    ]
    assert len(results) == 3
    ids = [c.id for c in results]
    assert ids.count("c_shared") == 1
    assert set(ids) == {"c1", "c2", "c_shared"}

    # Distances must be sorted ascending
    distances = [c.distance for c in results]
    assert distances == sorted(distances)


@pytest.mark.asyncio
async def test_empty_or_whitespace_targets_gracefully_return_empty_list() -> None:
    """Empty or whitespace-only target lists return empty list without raising exceptions."""
    embedder = SectionEmbedder()

    # Empty list
    res1 = await retrieve_multi_section(
        doc_hash="c" * 64,
        targets=[],
        embed_fn=embedder,
    )
    assert res1 == []

    # Whitespace-only targets
    res2 = await retrieve_multi_section(
        doc_hash="c" * 64,
        targets=["", "   ", "\t\n"],
        embed_fn=embedder,
    )
    assert res2 == []

    # None target
    res3 = await retrieve_multi_section(
        doc_hash="c" * 64,
        targets=None,
        embed_fn=embedder,
    )
    assert res3 == []


@pytest.mark.asyncio
async def test_each_pass_queries_with_semantically_expanded_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each retrieval pass queries retrieve() with a semantically expanded target name."""
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

    embedder = SectionEmbedder()
    await retrieve_multi_section(
        doc_hash="d" * 64,
        targets=["  abstract  ", "findings\n", "methodology", "conclusion"],
        embed_fn=embedder,
    )

    assert recorded_queries == [
        "Abstract background objective methods results conclusion",
        "Results findings data analysis outcomes",
        "Methodology methods participants instruments procedure design",
        "Conclusion summary implications findings",
    ]


@pytest.mark.asyncio
async def test_semantic_expansion_unmapped_targets_remain_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unmapped section targets pass through without modification."""
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

    embedder = SectionEmbedder()
    await retrieve_multi_section(
        doc_hash="d" * 64,
        targets=["discussion", "limitations"],
        embed_fn=embedder,
    )

    assert recorded_queries == ["discussion", "limitations"]


@pytest.mark.asyncio
async def test_guaranteed_page_1_abstract_when_vector_search_misses_page_1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When targets include 'abstract' and vector search misses Page 1, Page 1 is retrieved directly from Chroma."""
    doc_hash = "f" * 64
    chroma_client = chromadb.PersistentClient(path=str(tmp_path / "chroma_p1"))
    embedder = SectionEmbedder()

    chunks = [
        {"text": "Page 1 Abstract: The main proposal and contributions.", "page": 1},
        {"text": "Page 4 Header: Journal header mentioning abstract.", "page": 4},
        {"text": "Page 6 Header: Another journal header abstract.", "page": 6},
        {"text": "Page 15 Header: Third journal header abstract.", "page": 15},
        {"text": "Page 3 Results: We achieve 95% accuracy.", "page": 3},
    ]
    await index_document(
        doc_hash=doc_hash,
        chunks=chunks,
        embed_fn=embedder,
        client=chroma_client,
    )

    # Simulate vector search returning only pages 4, 6, 15 (dropping page 1)
    async def fake_retrieve(
        doc_hash: str,
        query: str,
        embed_fn: Any,
        top_k: int = 5,
        client: Any = None,
    ) -> list[RetrievedChunk]:
        if "Abstract" in query or "abstract" in query:
            return [
                RetrievedChunk(
                    id=f"{doc_hash}:1", text=chunks[1]["text"], page=4, distance=0.6
                ),
                RetrievedChunk(
                    id=f"{doc_hash}:2", text=chunks[2]["text"], page=6, distance=0.7
                ),
                RetrievedChunk(
                    id=f"{doc_hash}:3", text=chunks[3]["text"], page=15, distance=0.75
                ),
            ]
        elif "Results" in query or "results" in query:
            return [
                RetrievedChunk(
                    id=f"{doc_hash}:4", text=chunks[4]["text"], page=3, distance=0.2
                ),
            ]
        return []

    monkeypatch.setattr("app.services.qa.retrieve", fake_retrieve)

    results = await retrieve_multi_section(
        doc_hash=doc_hash,
        targets=["abstract", "results"],
        embed_fn=embedder,
        client=chroma_client,
        top_k=3,
    )

    # Page 1 should be guaranteed despite fake_retrieve dropping it
    pages = [c.page for c in results]
    assert 1 in pages
    assert 3 in pages

    # The guaranteed Page 1 chunk has distance 0.0, so it appears first
    p1_chunk = next(c for c in results if c.page == 1)
    assert p1_chunk.distance == 0.0
    assert "Page 1 Abstract" in p1_chunk.text
    assert results[0].page == 1


@pytest.mark.asyncio
async def test_relevance_threshold_filtering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Chunks with distance exceeding relevance_threshold are filtered out."""

    async def fake_retrieve(
        doc_hash: str,
        query: str,
        embed_fn: Any,
        top_k: int = 5,
        client: Any = None,
    ) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(id="c1", text="Close chunk", page=1, distance=0.5),
            RetrievedChunk(id="c2", text="Far chunk", page=2, distance=2.5),
        ]

    monkeypatch.setattr("app.services.qa.retrieve", fake_retrieve)

    embedder = SectionEmbedder()
    results = await retrieve_multi_section(
        doc_hash="e" * 64,
        targets=["abstract"],
        embed_fn=embedder,
        relevance_threshold=2.0,
    )

    assert len(results) == 1
    assert results[0].id == "c1"


@pytest.mark.asyncio
async def test_page_1_bypass_when_abstract_not_in_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When 'abstract' is not in targets, Chroma is not queried for Page 1 even if all chunks have page > 1."""

    async def fake_retrieve(
        doc_hash: str,
        query: str,
        embed_fn: Any,
        top_k: int = 5,
        client: Any = None,
    ) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(id="c1", text="Results page 3", page=3, distance=0.2),
            RetrievedChunk(id="c2", text="Methodology page 2", page=2, distance=0.3),
        ]

    monkeypatch.setattr("app.services.qa.retrieve", fake_retrieve)

    embedder = SectionEmbedder()
    results = await retrieve_multi_section(
        doc_hash="g" * 64,
        targets=["results", "methodology"],
        embed_fn=embedder,
    )

    pages = [c.page for c in results]
    assert 1 not in pages
    assert set(pages) == {2, 3}
