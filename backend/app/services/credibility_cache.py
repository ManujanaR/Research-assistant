"""Cache layer for external credibility verification results with 30-day TTL."""

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CREDIBILITY_CACHE_TTL_SECONDS = 30 * 86400  # 30 days


def _sanitize_cache_key(key: str) -> str:
    """Sanitize cache key for safe filename usage."""
    return re.sub(r"[^\w\-.]", "_", key)


class CredibilityCache:
    """Thread-safe two-tier (memory + disk) cache for external credibility records with TTL."""

    def __init__(self, cache_dir: Path | str | None = None) -> None:
        if cache_dir is None:
            self.cache_dir = Path(get_settings().credibility_cache_dir)
        else:
            self.cache_dir = Path(cache_dir)

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._memory: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve cached external record by key if not expired."""
        now = time.time()

        # Check memory
        if key in self._memory:
            entry = self._memory[key]
            if now - entry.get("timestamp", 0) <= CREDIBILITY_CACHE_TTL_SECONDS:
                logger.debug("Credibility cache hit (memory): %s", key)
                return entry.get("data")
            # Expired
            del self._memory[key]

        # Check disk
        safe_filename = f"{_sanitize_cache_key(key)}.json"
        file_path = self.cache_dir / safe_filename
        if file_path.is_file():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    entry = json.load(f)
                if now - entry.get("timestamp", 0) <= CREDIBILITY_CACHE_TTL_SECONDS:
                    self._memory[key] = entry
                    logger.debug("Credibility cache hit (disk): %s", key)
                    return entry.get("data")
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "Failed to read credibility disk cache for %s: %s", key, exc
                )

        return None

    def set(self, key: str, data: dict[str, Any]) -> None:
        """Store external record in memory and disk cache with current timestamp."""
        entry = {
            "timestamp": time.time(),
            "data": data,
        }
        self._memory[key] = entry

        safe_filename = f"{_sanitize_cache_key(key)}.json"
        file_path = self.cache_dir / safe_filename
        try:
            temp_path = self.cache_dir / f"{safe_filename}.tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(entry, f)
            temp_path.replace(file_path)
            logger.debug("Stored credibility cache entry: %s", key)
        except OSError as exc:
            logger.warning(
                "Failed to write credibility cache file for %s: %s", key, exc
            )

    def clear(self) -> None:
        """Clear memory cache."""
        self._memory.clear()
