import json
import logging
import os
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

HEX_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SummaryCache:
    """Two-layer summary cache with in-memory store and atomic disk fallback."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, dict[str, Any]] = {}

    def _validate_hash(self, doc_hash: str) -> None:
        """Validate that doc_hash consists strictly of 64 lowercase hexadecimal characters."""
        if not isinstance(doc_hash, str) or not HEX_SHA256_PATTERN.match(doc_hash):
            raise ValueError(f"Invalid SHA-256 hash: {doc_hash!r}")

    def get(self, doc_hash: str) -> dict[str, Any] | None:
        """Retrieve cached summary by document hash, checking memory first, then disk."""
        self._validate_hash(doc_hash)

        if doc_hash in self._memory:
            logger.debug("Summary cache hit (memory): %s", doc_hash)
            return self._memory[doc_hash]

        file_path = self.cache_dir / f"{doc_hash}.json"
        if file_path.is_file():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data: dict[str, Any] = json.load(f)
                self._memory[doc_hash] = data
                logger.debug("Summary cache hit (disk): %s", doc_hash)
                return data
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Failed to read disk cache for %s: %s", doc_hash, exc)
                return None

        logger.debug("Summary cache miss: %s", doc_hash)
        return None

    def set(self, doc_hash: str, value: dict[str, Any]) -> None:
        """Store summary in memory and write atomically to disk."""
        self._validate_hash(doc_hash)
        self._memory[doc_hash] = value

        final_path = self.cache_dir / f"{doc_hash}.json"
        tmp_path = self.cache_dir / f"{doc_hash}.tmp"

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, final_path)
            logger.debug("Summary cached to disk: %s", final_path)
        except Exception:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            raise

    def clear_memory(self) -> None:
        """Clear the in-memory cache layer."""
        self._memory.clear()
