import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

HEX_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SUMMARY_VERSION = 2


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

    def get(
        self, doc_hash: str, expected_model: str | None = None
    ) -> dict[str, Any] | None:
        """Retrieve cached summary by document hash, checking memory first, then disk.

        Treats entry as a miss if its stored model_name differs from expected_model
        (defaults to settings.model_name). Logs a WARNING on model mismatch.
        """
        self._validate_hash(doc_hash)
        if expected_model is None:
            expected_model = get_settings().model_name

        data: dict[str, Any] | None = None
        if doc_hash in self._memory:
            logger.debug("Summary cache hit (memory): %s", doc_hash)
            data = self._memory[doc_hash]
        else:
            file_path = self.cache_dir / f"{doc_hash}.json"
            if file_path.is_file():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._memory[doc_hash] = data
                    logger.debug("Summary cache hit (disk): %s", doc_hash)
                except (OSError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "Failed to read disk cache for %s: %s", doc_hash, exc
                    )
                    return None

        if data is None:
            logger.debug("Summary cache miss: %s", doc_hash)
            return None

        if isinstance(data, dict) and "model_name" in data and "summary" in data:
            stored_version = data.get("version")
            if stored_version != SUMMARY_VERSION:
                logger.warning(
                    "Summary cache miss for %s: cached version '%s' differs from required version '%s'",
                    doc_hash,
                    stored_version,
                    SUMMARY_VERSION,
                )
                return None
            stored_model = data.get("model_name")
            if stored_model != expected_model:
                logger.warning(
                    "Summary cache miss for %s: cached model '%s' differs from configured model '%s'",
                    doc_hash,
                    stored_model,
                    expected_model,
                )
                return None
            return data["summary"]

        if isinstance(data, dict):
            logger.warning(
                "Summary cache miss for %s: entry missing model_name",
                doc_hash,
            )
            return None

        return None

    def set(
        self,
        doc_hash: str,
        value: dict[str, Any],
        model_name: str | None = None,
    ) -> None:
        """Store summary in memory and write atomically to disk alongside model_name."""
        self._validate_hash(doc_hash)
        if model_name is None:
            model_name = get_settings().model_name

        payload = {
            "version": SUMMARY_VERSION,
            "model_name": model_name,
            "summary": value,
        }
        self._memory[doc_hash] = payload

        final_path = self.cache_dir / f"{doc_hash}.json"
        tmp_path = self.cache_dir / f"{doc_hash}.tmp"

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
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
