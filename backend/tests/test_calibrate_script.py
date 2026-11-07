"""Unit tests for scripts/calibrate_citation_threshold.py."""

from pathlib import Path
from unittest.mock import patch

import chromadb
import pytest

from app.core.config import Settings
from scripts.calibrate_citation_threshold import main


@pytest.fixture
def fake_doc_hash() -> str:
    return "a" * 64


def test_separable_groups_suggests_midpoint(
    tmp_path: Path, fake_doc_hash: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """When on-topic distance is strictly lower than off-topic distance, midpoint is suggested."""
    chroma_dir = tmp_path / "chroma"
    client = chromadb.PersistentClient(path=str(chroma_dir))
    coll = client.create_collection(
        name=f"doc_{fake_doc_hash[:32]}",
        metadata={"embedding_model": "test-embed-model", "hnsw:space": "cosine"},
    )
    # Add document chunk with vector [1.0, 0.0]
    coll.add(
        ids=["chunk_1"],
        documents=["This paper discusses transformer architectures."],
        embeddings=[[1.0, 0.0]],
    )

    async def fake_embed_fn(texts: list[str]) -> list[list[float]]:
        # On-topic questions return vector very close to [1.0, 0.0] (dist ~0.0)
        # Off-topic questions return vector orthogonal [0.0, 1.0] (dist = 1.0)
        res: list[list[float]] = []
        for t in texts:
            if "transformer" in t.lower():
                res.append([1.0, 0.0])
            else:
                res.append([0.0, 1.0])
        return res

    settings = Settings(
        EMBEDDING_MODEL="test-embed-model",
        CHROMA_DIR=str(chroma_dir),
        _env_file=None,
    )

    with (
        patch(
            "scripts.calibrate_citation_threshold.get_settings", return_value=settings
        ),
        patch(
            "scripts.calibrate_citation_threshold.get_chroma_client",
            return_value=client,
        ),
        patch(
            "scripts.calibrate_citation_threshold.get_embedding_function",
            return_value=fake_embed_fn,
        ),
    ):
        code = main(
            [
                "--doc-hash",
                fake_doc_hash,
                "--on-topic",
                "What is the transformer architecture?",
                "--off-topic",
                "What is the weather in Tokyo?",
            ]
        )

    captured = capsys.readouterr()
    assert code == 0
    assert "Separable: True" in captured.out
    assert "Suggested CITATION_MAX_DISTANCE:" in captured.out
    # Distance between [1,0] and [1,0] is 0.0, between [1,0] and [0,1] is 1.0. Midpoint is 0.5000.
    assert "0.5000" in captured.out


def test_overlapping_groups_suggests_no_threshold(
    tmp_path: Path, fake_doc_hash: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """When off-topic distance is lower than on-topic distance, script reports overlap and no threshold."""
    chroma_dir = tmp_path / "chroma"
    client = chromadb.PersistentClient(path=str(chroma_dir))
    coll = client.create_collection(
        name=f"doc_{fake_doc_hash[:32]}",
        metadata={"embedding_model": "test-embed-model", "hnsw:space": "cosine"},
    )
    coll.add(
        ids=["chunk_1"],
        documents=["Sample document text."],
        embeddings=[[1.0, 0.0]],
    )

    async def fake_embed_fn(texts: list[str]) -> list[list[float]]:
        # Inverted: on-topic gets orthogonal vector [0.0, 1.0] (dist = 1.0),
        # off-topic gets identical vector [1.0, 0.0] (dist = 0.0)
        res: list[list[float]] = []
        for t in texts:
            if "on-topic" in t.lower():
                res.append([0.0, 1.0])
            else:
                res.append([1.0, 0.0])
        return res

    settings = Settings(
        EMBEDDING_MODEL="test-embed-model",
        CHROMA_DIR=str(chroma_dir),
        _env_file=None,
    )

    with (
        patch(
            "scripts.calibrate_citation_threshold.get_settings", return_value=settings
        ),
        patch(
            "scripts.calibrate_citation_threshold.get_chroma_client",
            return_value=client,
        ),
        patch(
            "scripts.calibrate_citation_threshold.get_embedding_function",
            return_value=fake_embed_fn,
        ),
    ):
        code = main(
            [
                "--doc-hash",
                fake_doc_hash,
                "--on-topic",
                "on-topic question",
                "--off-topic",
                "off-topic question",
            ]
        )

    captured = capsys.readouterr()
    assert code == 0
    assert "Separable: False" in captured.out
    assert "The groups overlap; suggest no threshold." in captured.out
    assert (
        "1 off-topic question(s) fall below the highest on-topic distance."
        in captured.out
    )


def test_missing_collection_exits_with_upload_message(
    tmp_path: Path, fake_doc_hash: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """When Chroma collection does not exist, exits 1 with a clear upload message."""
    chroma_dir = tmp_path / "chroma_empty"
    client = chromadb.PersistentClient(path=str(chroma_dir))

    settings = Settings(
        EMBEDDING_MODEL="test-embed-model",
        CHROMA_DIR=str(chroma_dir),
        _env_file=None,
    )

    with (
        patch(
            "scripts.calibrate_citation_threshold.get_settings", return_value=settings
        ),
        patch(
            "scripts.calibrate_citation_threshold.get_chroma_client",
            return_value=client,
        ),
    ):
        code = main(
            [
                "--doc-hash",
                fake_doc_hash,
                "--on-topic",
                "Question 1?",
                "--off-topic",
                "Question 2?",
            ]
        )

    captured = capsys.readouterr()
    assert code == 1
    assert "The paper must be uploaded first." in captured.err


def test_model_mismatch_prints_warning(
    tmp_path: Path, fake_doc_hash: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """When configured EMBEDDING_MODEL differs from stored embedding_model, WARNING is printed."""
    chroma_dir = tmp_path / "chroma"
    client = chromadb.PersistentClient(path=str(chroma_dir))
    coll = client.create_collection(
        name=f"doc_{fake_doc_hash[:32]}",
        metadata={"embedding_model": "old-stored-model", "hnsw:space": "cosine"},
    )
    coll.add(
        ids=["chunk_1"],
        documents=["Sample text."],
        embeddings=[[1.0, 0.0]],
    )

    async def fake_embed_fn(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    settings = Settings(
        EMBEDDING_MODEL="new-configured-model",
        CHROMA_DIR=str(chroma_dir),
        _env_file=None,
    )

    with (
        patch(
            "scripts.calibrate_citation_threshold.get_settings", return_value=settings
        ),
        patch(
            "scripts.calibrate_citation_threshold.get_chroma_client",
            return_value=client,
        ),
        patch(
            "scripts.calibrate_citation_threshold.get_embedding_function",
            return_value=fake_embed_fn,
        ),
    ):
        code = main(
            [
                "--doc-hash",
                fake_doc_hash,
                "--on-topic",
                "Sample question?",
                "--off-topic",
                "Random question?",
            ]
        )

    captured = capsys.readouterr()
    assert code == 0
    assert "WARNING:" in captured.out
    assert "new-configured-model" in captured.out
    assert "old-stored-model" in captured.out


def test_the_key_is_never_printed(
    tmp_path: Path, fake_doc_hash: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The API key string is never printed to stdout or stderr."""
    chroma_dir = tmp_path / "chroma"
    client = chromadb.PersistentClient(path=str(chroma_dir))
    coll = client.create_collection(
        name=f"doc_{fake_doc_hash[:32]}",
        metadata={"embedding_model": "test-embed-model", "hnsw:space": "cosine"},
    )
    coll.add(
        ids=["chunk_1"],
        documents=["Sample text."],
        embeddings=[[1.0, 0.0]],
    )

    secret_key = "sk-super-secret-canary-key-99999-do-not-leak"

    async def fake_embed_fn(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    settings = Settings(
        OPENAI_API_KEY=secret_key,
        EMBEDDING_MODEL="test-embed-model",
        CHROMA_DIR=str(chroma_dir),
        _env_file=None,
    )

    with (
        patch(
            "scripts.calibrate_citation_threshold.get_settings", return_value=settings
        ),
        patch(
            "scripts.calibrate_citation_threshold.get_chroma_client",
            return_value=client,
        ),
        patch(
            "scripts.calibrate_citation_threshold.get_embedding_function",
            return_value=fake_embed_fn,
        ),
    ):
        code = main(
            [
                "--doc-hash",
                fake_doc_hash,
                "--on-topic",
                "On-topic question?",
                "--off-topic",
                "Off-topic question?",
            ]
        )

    captured = capsys.readouterr()
    assert code == 0
    assert secret_key not in captured.out
    assert secret_key not in captured.err


def test_argument_validation(capsys: pytest.CaptureFixture[str]) -> None:
    """Invalid doc_hash or missing on-topic/off-topic questions exits with code 1."""
    # Invalid doc-hash
    code_invalid_hash = main(
        [
            "--doc-hash",
            "not-a-valid-hash",
            "--on-topic",
            "Q1",
            "--off-topic",
            "Q2",
        ]
    )
    assert code_invalid_hash == 1
    assert "Invalid --doc-hash" in capsys.readouterr().err

    # Missing on-topic
    code_no_ontopic = main(
        [
            "--doc-hash",
            "b" * 64,
            "--off-topic",
            "Q2",
        ]
    )
    assert code_no_ontopic == 1
    assert "At least one --on-topic question is required." in capsys.readouterr().err

    # Missing off-topic
    code_no_offtopic = main(
        [
            "--doc-hash",
            "c" * 64,
            "--on-topic",
            "Q1",
        ]
    )
    assert code_no_offtopic == 1
    assert "At least one --off-topic question is required." in capsys.readouterr().err
