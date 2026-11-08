import hashlib
import json
import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.config import Settings, get_settings
from app.core.dependencies import (
    get_llm_client,
    get_paper_text_store,
    get_summary_cache,
)
from app.main import app
from app.services.cache import SummaryCache
from app.services.summarizer import SUMMARY_GENERATION_FAILED_MESSAGE
from app.services.summary_service import InMemoryPaperTextStore
from tests.conftest import AuthenticatedTestClient
from tests.test_summarizer import VALID_SUMMARY_DICT, FakeOpenAIClient

VALID_HASH = hashlib.sha256(b"commit 7 test paper bytes").hexdigest()


@pytest.fixture
def clean_environment(
    tmp_path: Path,
) -> Generator[tuple[SummaryCache, InMemoryPaperTextStore], None, None]:
    """Provide isolated cache and text store, restoring dependency overrides and settings."""
    cache = SummaryCache(cache_dir=tmp_path)
    text_store = InMemoryPaperTextStore()

    app.dependency_overrides[get_summary_cache] = lambda: cache
    app.dependency_overrides[get_paper_text_store] = lambda: text_store

    get_settings.cache_clear()
    yield cache, text_store

    app.dependency_overrides.pop(get_summary_cache, None)
    app.dependency_overrides.pop(get_paper_text_store, None)
    app.dependency_overrides.pop(get_llm_client, None)
    get_settings.cache_clear()


def test_default_summary_cache_dir_setting() -> None:
    """Verify that summary_cache_dir defaults to .cache/summaries resolved to absolute path."""
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=None)
        assert Path(settings.summary_cache_dir).is_absolute()
        assert settings.summary_cache_dir.endswith(".cache/summaries")


def test_summary_cache_hit(
    auth_client: AuthenticatedTestClient,
    clean_environment: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """Verify that a cache hit returns 200 and does not construct or call the LLM client."""
    cache, _ = clean_environment
    cache.set(VALID_HASH, VALID_SUMMARY_DICT)
    auth_client.record_ownership(VALID_HASH)

    fake_client = FakeOpenAIClient([])
    app.dependency_overrides[get_llm_client] = lambda: fake_client

    response = auth_client.post("/api/summary", json={"doc_hash": VALID_HASH})
    assert response.status_code == 200
    assert response.json() == VALID_SUMMARY_DICT
    assert len(fake_client.chat.completions.calls) == 0


def test_summary_cache_miss_with_text_present(
    auth_client: AuthenticatedTestClient,
    clean_environment: tuple[SummaryCache, InMemoryPaperTextStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that cache miss generates summary, caches it, and subsequent call hits cache."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-test-key")
    get_settings.cache_clear()

    _, text_store = clean_environment
    text_store.set_text(VALID_HASH, "Sample extracted paper text.")
    auth_client.record_ownership(VALID_HASH)

    fake_client = FakeOpenAIClient([json.dumps(VALID_SUMMARY_DICT)])
    app.dependency_overrides[get_llm_client] = lambda: fake_client

    # First call: cache miss -> generates summary
    resp1 = auth_client.post("/api/summary", json={"doc_hash": VALID_HASH})
    assert resp1.status_code == 200
    assert resp1.json() == VALID_SUMMARY_DICT
    assert len(fake_client.chat.completions.calls) == 1

    # Second call: cache hit -> returns without additional client calls
    resp2 = auth_client.post("/api/summary", json={"doc_hash": VALID_HASH})
    assert resp2.status_code == 200
    assert resp2.json() == VALID_SUMMARY_DICT
    assert len(fake_client.chat.completions.calls) == 1


def test_cache_entry_with_older_version_is_a_miss_and_regenerated(
    auth_client: AuthenticatedTestClient,
    clean_environment: tuple[SummaryCache, InMemoryPaperTextStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a cached entry with version 1 is treated as a miss and is regenerated."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-test-key")
    get_settings.cache_clear()

    cache, text_store = clean_environment
    text_store.set_text(VALID_HASH, "Sample extracted paper text.")
    auth_client.record_ownership(VALID_HASH)

    # Store entry with version 1 directly in memory
    old_version_entry = {
        "version": 1,
        "model_name": get_settings().model_name,
        "summary": {
            "title_authors_abstract": "Old title - Authors - Abstract",
            "problem_statement": "Old problem",
            "methodology": "Old methodology",
            "key_results": "Old results",
            "conclusion": "Old conclusion",
        },
    }
    cache._memory[VALID_HASH] = old_version_entry

    fake_client = FakeOpenAIClient([json.dumps(VALID_SUMMARY_DICT)])
    app.dependency_overrides[get_llm_client] = lambda: fake_client

    response = auth_client.post("/api/summary", json={"doc_hash": VALID_HASH})
    assert response.status_code == 200
    assert response.json() == VALID_SUMMARY_DICT
    # Must have called LLM because version 1 was treated as a miss
    assert len(fake_client.chat.completions.calls) == 1

    # Verify that the newly cached entry has version 2
    cached_payload = cache._memory.get(VALID_HASH)
    assert cached_payload is not None
    assert cached_payload.get("version") == 2


def test_summary_cache_miss_summarizer_fails_after_retry(
    auth_client: AuthenticatedTestClient,
    clean_environment: tuple[SummaryCache, InMemoryPaperTextStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that permanent validation failure returns HTTP 502 with exact constant message."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-test-key")
    get_settings.cache_clear()

    _, text_store = clean_environment
    text_store.set_text(VALID_HASH, "Sample extracted paper text.")
    auth_client.record_ownership(VALID_HASH)

    fake_client = FakeOpenAIClient(["malformed json 1", "malformed json 2"])
    app.dependency_overrides[get_llm_client] = lambda: fake_client

    response = auth_client.post("/api/summary", json={"doc_hash": VALID_HASH})
    assert response.status_code == 502
    assert response.json() == {"detail": SUMMARY_GENERATION_FAILED_MESSAGE}


def test_summary_cache_miss_text_missing(
    auth_client: AuthenticatedTestClient,
    clean_environment: tuple[SummaryCache, InMemoryPaperTextStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that missing paper text on cache miss returns HTTP 404 with exact message."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-test-key")
    get_settings.cache_clear()
    auth_client.record_ownership(VALID_HASH)

    fake_client = FakeOpenAIClient([])
    app.dependency_overrides[get_llm_client] = lambda: fake_client

    response = auth_client.post("/api/summary", json={"doc_hash": VALID_HASH})
    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found. Upload the PDF first."}
    assert len(fake_client.chat.completions.calls) == 0


@pytest.mark.parametrize(
    "invalid_hash",
    [
        "../etc/passwd",
        "abcd1234",
        "A" * 64,
    ],
)
def test_summary_invalid_hashes_return_422(
    auth_client: AuthenticatedTestClient, invalid_hash: str
) -> None:
    """Verify that invalid hashes return HTTP 422 Unprocessable Entity."""
    response = auth_client.post("/api/summary", json={"doc_hash": invalid_hash})
    assert response.status_code == 422


def test_summary_cache_hit_with_no_openai_api_key(
    auth_client: AuthenticatedTestClient,
    clean_environment: tuple[SummaryCache, InMemoryPaperTextStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a cache hit returns HTTP 200 even when OPENAI_API_KEY is unset."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()

    cache, _ = clean_environment
    cache.set(VALID_HASH, VALID_SUMMARY_DICT)
    auth_client.record_ownership(VALID_HASH)

    try:
        response = auth_client.post("/api/summary", json={"doc_hash": VALID_HASH})
        assert response.status_code == 200
        assert response.json() == VALID_SUMMARY_DICT
    finally:
        get_settings.cache_clear()


def test_summary_cache_miss_with_no_openai_api_key(
    auth_client: AuthenticatedTestClient,
    clean_environment: tuple[SummaryCache, InMemoryPaperTextStore],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that a cache miss returns HTTP 503 when OPENAI_API_KEY is not configured."""
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    auth_client.record_ownership(VALID_HASH)

    # Ensure no LLM client override is active
    if get_llm_client in app.dependency_overrides:
        del app.dependency_overrides[get_llm_client]

    try:
        response = auth_client.post("/api/summary", json={"doc_hash": VALID_HASH})
        assert response.status_code == 503
        assert response.json() == {"detail": "OpenAI API key is not configured."}
    finally:
        get_settings.cache_clear()
