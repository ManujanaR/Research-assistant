import hashlib
from pathlib import Path

import pytest

from app.services.cache import SummaryCache

VALID_HASH = hashlib.sha256(b"sample pdf content").hexdigest()
SAMPLE_SUMMARY = {
    "title_authors_abstract": "Sample Title - Author - Abstract text",
    "problem_statement": "Problem statement text",
    "methodology": "Methodology description",
    "key_results": "Key results description",
    "conclusion": "Conclusion text",
}


def test_cache_miss_on_empty(tmp_path: Path) -> None:
    """Verify that querying an empty cache returns None."""
    cache = SummaryCache(cache_dir=tmp_path)
    assert cache.get(VALID_HASH) is None


def test_set_then_get_memory_hit(tmp_path: Path) -> None:
    """Verify that set followed by get returns the identical stored dict."""
    cache = SummaryCache(cache_dir=tmp_path)
    cache.set(VALID_HASH, SAMPLE_SUMMARY)
    result = cache.get(VALID_HASH)
    assert result == SAMPLE_SUMMARY


def test_identical_and_differing_bytes_hash_keys() -> None:
    """Verify that identical byte streams yield identical keys and differing bytes yield different keys."""
    bytes_a1 = b"%PDF-1.4 paper content version 1"
    bytes_a2 = b"%PDF-1.4 paper content version 1"
    bytes_b = b"%PDF-1.4 paper content version 2 (altered)"

    hash_a1 = hashlib.sha256(bytes_a1).hexdigest()
    hash_a2 = hashlib.sha256(bytes_a2).hexdigest()
    hash_b = hashlib.sha256(bytes_b).hexdigest()

    assert hash_a1 == hash_a2
    assert hash_a1 != hash_b
    assert len(hash_a1) == 64
    assert len(hash_b) == 64


def test_disk_fallback_across_instances(tmp_path: Path) -> None:
    """Verify disk persistence across separate SummaryCache instances pointing to the same directory."""
    cache_inst1 = SummaryCache(cache_dir=tmp_path)
    cache_inst1.set(VALID_HASH, SAMPLE_SUMMARY)

    # Second instance with fresh in-memory state
    cache_inst2 = SummaryCache(cache_dir=tmp_path)
    assert VALID_HASH not in cache_inst2._memory

    # Should recover from disk
    result = cache_inst2.get(VALID_HASH)
    assert result == SAMPLE_SUMMARY
    assert VALID_HASH in cache_inst2._memory


def test_clear_memory_recovers_from_disk(tmp_path: Path) -> None:
    """Verify that clearing in-memory cache layer falls back to disk on subsequent get."""
    cache = SummaryCache(cache_dir=tmp_path)
    cache.set(VALID_HASH, SAMPLE_SUMMARY)
    assert VALID_HASH in cache._memory

    cache.clear_memory()
    assert len(cache._memory) == 0

    recovered = cache.get(VALID_HASH)
    assert recovered == SAMPLE_SUMMARY
    assert VALID_HASH in cache._memory


@pytest.mark.parametrize(
    "invalid_key",
    [
        "",  # Empty string
        "abcd1234",  # Short hex string
        "A" * 64,  # Uppercase hex string
        "../etc/passwd",  # Path traversal attempt
        "../../doc.json",  # Directory traversal
        "not_a_hex_hash_at_all_1234567890abcdef1234567890abcdef1234567890abc",
    ],
)
def test_invalid_hash_keys_raise_value_error(tmp_path: Path, invalid_key: str) -> None:
    """Verify that non-64 lowercase hex keys raise ValueError on get and set."""
    cache = SummaryCache(cache_dir=tmp_path)

    with pytest.raises(ValueError):
        cache.get(invalid_key)

    with pytest.raises(ValueError):
        cache.set(invalid_key, SAMPLE_SUMMARY)


def test_atomic_write_leaves_no_tmp_files(tmp_path: Path) -> None:
    """Verify that atomic write cleans up all temporary .tmp files."""
    cache = SummaryCache(cache_dir=tmp_path)
    cache.set(VALID_HASH, SAMPLE_SUMMARY)

    final_file = tmp_path / f"{VALID_HASH}.json"
    assert final_file.is_file()

    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Expected no .tmp files, found: {tmp_files}"
