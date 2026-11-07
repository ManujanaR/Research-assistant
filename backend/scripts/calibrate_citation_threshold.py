"""Script to calibrate the CITATION_MAX_DISTANCE threshold for a given embedding model."""

import argparse
import asyncio
import sys
from pathlib import Path

# Ensure backend root is on sys.path when invoked directly
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import chromadb.errors
from chromadb.api import ClientAPI

from app.core.config import get_settings
from app.core.dependencies import get_chroma_client, get_embedding_function
from app.services.cache import HEX_SHA256_PATTERN
from app.services.qa import EmbedFn


async def run_calibration(
    doc_hash: str,
    on_topic: list[str],
    off_topic: list[str],
    client: ClientAPI | None = None,
    embed_fn: EmbedFn | None = None,
) -> int:
    """Run calibration against Chroma collection and report distances and suggested cutoff."""
    settings = get_settings()
    client = client or get_chroma_client()
    embed_fn = embed_fn or get_embedding_function()

    collection_name = f"doc_{doc_hash[:32]}"
    try:
        collection = client.get_collection(name=collection_name)
    except (chromadb.errors.ChromaError, ValueError, KeyError) as exc:
        print(
            f"Error: Chroma collection '{collection_name}' not found ({exc}). The paper must be uploaded first.",
            file=sys.stderr,
        )
        return 1

    if collection.count() == 0:
        print(
            f"Error: Chroma collection '{collection_name}' is empty. The paper must be uploaded first.",
            file=sys.stderr,
        )
        return 1

    configured_model = settings.embedding_model
    coll_meta = collection.metadata or {}
    stored_model = coll_meta.get("embedding_model")

    print(f"Configured EMBEDDING_MODEL: {configured_model}")
    print(f"Stored collection embedding_model: {stored_model}")
    if stored_model and stored_model != configured_model:
        print(
            f"WARNING: Configured EMBEDDING_MODEL '{configured_model}' differs from "
            f"stored collection embedding_model '{stored_model}'."
        )

    # 1. On-topic evaluation
    print("\nOn-topic questions:")
    on_topic_all_dists: list[float] = []
    for q in on_topic:
        q_emb = await embed_fn([q])
        n_results = min(5, collection.count())
        res = collection.query(
            query_embeddings=q_emb,
            n_results=n_results,
            include=["distances"],
        )
        raw_dists = res.get("distances", [[]])[0]
        dists = [float(d) for d in raw_dists]
        on_topic_all_dists.extend(dists)
        formatted = ", ".join(f"{d:.4f}" for d in dists)
        print(f"  Question: {q}")
        print(f"  Distances: [{formatted}]")

    # 2. Off-topic evaluation
    print("\nOff-topic questions:")
    off_topic_all_dists: list[float] = []
    off_topic_q_min_dists: list[float] = []
    for q in off_topic:
        q_emb = await embed_fn([q])
        n_results = min(5, collection.count())
        res = collection.query(
            query_embeddings=q_emb,
            n_results=n_results,
            include=["distances"],
        )
        raw_dists = res.get("distances", [[]])[0]
        dists = [float(d) for d in raw_dists]
        off_topic_all_dists.extend(dists)
        if dists:
            off_topic_q_min_dists.append(min(dists))
        formatted = ", ".join(f"{d:.4f}" for d in dists)
        print(f"  Question: {q}")
        print(f"  Distances: [{formatted}]")

    # 3. Separation analysis
    highest_on_topic = max(on_topic_all_dists) if on_topic_all_dists else 0.0
    lowest_off_topic = min(off_topic_all_dists) if off_topic_all_dists else 0.0
    separable = highest_on_topic < lowest_off_topic

    print("\nAnalysis:")
    print(f"Highest on-topic distance: {highest_on_topic:.4f}")
    print(f"Lowest off-topic distance: {lowest_off_topic:.4f}")
    print(f"Separable: {separable}")

    if separable:
        midpoint = (highest_on_topic + lowest_off_topic) / 2.0
        print(f"Suggested CITATION_MAX_DISTANCE: {midpoint:.4f}")
    else:
        overlapping_count = sum(
            1 for min_d in off_topic_q_min_dists if min_d <= highest_on_topic
        )
        print("The groups overlap; suggest no threshold.")
        print(
            f"{overlapping_count} off-topic question(s) fall below the highest on-topic distance."
        )

    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for calibration script."""
    parser = argparse.ArgumentParser(
        description="Calibrate CITATION_MAX_DISTANCE for the current embedding model."
    )
    parser.add_argument(
        "--doc-hash",
        required=True,
        help="64-character lowercase hex SHA-256 hash of the uploaded document.",
    )
    parser.add_argument(
        "--on-topic",
        action="append",
        default=[],
        help="On-topic evaluation question (repeatable, at least one required).",
    )
    parser.add_argument(
        "--off-topic",
        action="append",
        default=[],
        help="Off-topic evaluation question (repeatable, at least one required).",
    )
    args = parser.parse_args(argv)

    if not HEX_SHA256_PATTERN.match(args.doc_hash):
        print(
            f"Error: Invalid --doc-hash '{args.doc_hash}'. Must be 64 lowercase hex characters.",
            file=sys.stderr,
        )
        return 1

    if not args.on_topic:
        print("Error: At least one --on-topic question is required.", file=sys.stderr)
        return 1

    if not args.off_topic:
        print("Error: At least one --off-topic question is required.", file=sys.stderr)
        return 1

    try:
        return asyncio.run(
            run_calibration(
                doc_hash=args.doc_hash,
                on_topic=args.on_topic,
                off_topic=args.off_topic,
            )
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Error during calibration: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
