import math
from typing import Any

_STORED_CHUNKS: list[dict[str, Any]] = []
_STORED_VECTORS: list[list[float]] = []


def store_chunks(
    chunks: list[dict[str, Any]], vectors: list[list[float]]
) -> None:
    global _STORED_CHUNKS, _STORED_VECTORS
    _STORED_CHUNKS = chunks
    _STORED_VECTORS = vectors


def has_index() -> bool:
    return len(_STORED_CHUNKS) > 0


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        dot += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def search(
    query_vector: list[float], top_k: int = 4
) -> list[dict[str, Any]]:
    if not _STORED_CHUNKS or not _STORED_VECTORS:
        return []

    scored_chunks: list[tuple[float, dict[str, Any]]] = []
    for chunk, vec in zip(_STORED_CHUNKS, _STORED_VECTORS):
        score = _cosine_similarity(query_vector, vec)
        scored_chunks.append((score, chunk))

    scored_chunks.sort(key=lambda x: x[0], reverse=True)

    results: list[dict[str, Any]] = []
    for score, chunk in scored_chunks[:top_k]:
        results.append(
            {
                "score": score,
                "page": chunk.get("page"),
                "section": chunk.get("section"),
                "text": chunk.get("text", ""),
            }
        )
    return results
