import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import chromadb
from chromadb.api import ClientAPI

from app.core.config import get_settings
from app.services.cache import HEX_SHA256_PATTERN

logger = logging.getLogger(__name__)

EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]


@dataclass
class RetrievedChunk:
    """A retrieved document chunk with page provenance and distance score."""

    text: str
    page: int
    distance: float


def _validate_hash(doc_hash: str) -> None:
    """Validate that doc_hash strictly conforms to the SHA-256 regex."""
    if not isinstance(doc_hash, str) or not HEX_SHA256_PATTERN.match(doc_hash):
        raise ValueError(f"Invalid SHA-256 hash: {doc_hash!r}")


def get_chroma_collection_name(doc_hash: str) -> str:
    """Return valid Chroma collection name: 'doc_' + first 32 hex chars."""
    _validate_hash(doc_hash)
    return "doc_" + doc_hash[:32]


async def index_document(
    doc_hash: str,
    chunks: list[dict[str, Any]],
    embed_fn: EmbedFn,
    client: ClientAPI | None = None,
) -> None:
    """Index document chunks into ChromaDB collection.

    Raises:
        ValueError: If doc_hash is invalid or if chunks is empty.
    """
    _validate_hash(doc_hash)
    if not chunks:
        raise ValueError("Document has zero chunks; cannot index.")

    if client is None:
        settings = get_settings()
        client = chromadb.PersistentClient(path=settings.chroma_dir)

    collection_name = get_chroma_collection_name(doc_hash)
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    # If already indexed with matching count, skip embedding
    current_count = collection.count()
    if current_count == len(chunks):
        logger.info(
            "Collection %s already indexed with %d chunks; skipping re-indexing",
            collection_name,
            current_count,
        )
        return

    # If count mismatch (e.g. previous partial write), reset collection
    if current_count > 0:
        logger.warning(
            "Collection %s has count mismatch (%d != %d); resetting collection",
            collection_name,
            current_count,
            len(chunks),
        )
        client.delete_collection(name=collection_name)
        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    logger.info(
        "Embedding and indexing %d chunks for doc_hash %s", len(chunks), doc_hash
    )
    texts = [str(c["text"]) for c in chunks]
    ids = [f"{doc_hash}:{i}" for i in range(len(chunks))]
    metadatas: list[dict[str, Any]] = [{"page": int(c["page"])} for c in chunks]

    embeddings = await embed_fn(texts)
    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings,
    )
    logger.info(
        "Successfully indexed %d chunks in collection %s", len(chunks), collection_name
    )


async def retrieve(
    doc_hash: str,
    query: str,
    embed_fn: EmbedFn,
    top_k: int = 5,
    client: ClientAPI | None = None,
) -> list[RetrievedChunk]:
    """Retrieve top-k relevant chunks for a query from the document's Chroma collection.

    Clamps top_k to stored chunk count. Page provenance comes strictly from metadata.
    """
    _validate_hash(doc_hash)

    if client is None:
        settings = get_settings()
        client = chromadb.PersistentClient(path=settings.chroma_dir)

    collection_name = get_chroma_collection_name(doc_hash)
    try:
        collection = client.get_collection(name=collection_name)
    except (chromadb.errors.ChromaError, ValueError, KeyError) as exc:
        logger.warning("Collection %s not found in Chroma: %s", collection_name, exc)
        return []

    total_count = collection.count()
    if total_count == 0:
        return []

    clamped_k = min(top_k, total_count)
    if clamped_k <= 0:
        return []

    query_embeddings = await embed_fn([query])
    query_result = collection.query(
        query_embeddings=query_embeddings,
        n_results=clamped_k,
    )

    retrieved: list[RetrievedChunk] = []
    docs = query_result.get("documents", [[]])[0]
    metas = query_result.get("metadatas", [[]])[0]
    distances = (
        query_result.get("distances", [[]])[0]
        if query_result.get("distances")
        else [0.0] * len(docs)
    )

    for doc_text, meta, dist in zip(docs, metas, distances, strict=False):
        page_num = int(meta.get("page", 1)) if meta else 1
        retrieved.append(
            RetrievedChunk(
                text=str(doc_text),
                page=page_num,
                distance=float(dist),
            )
        )

    return retrieved
