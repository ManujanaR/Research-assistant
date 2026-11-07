"""In-memory rate limiter for login protection."""

import threading
from collections import defaultdict
from datetime import UTC, datetime

MAX_FAILED_ATTEMPTS = 5
WINDOW_MINUTES = 15
WINDOW_SECONDS = WINDOW_MINUTES * 60


class LoginRateLimiter:
    """Sliding-window failure limiter tracking failed attempts per key (email or IP)."""

    def __init__(
        self,
        max_attempts: int = MAX_FAILED_ATTEMPTS,
        window_seconds: int = WINDOW_SECONDS,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._failures: dict[str, list[float]] = defaultdict(list)

    def _clean_expired(self, key: str, now: float) -> list[float]:
        threshold = now - self.window_seconds
        valid = [ts for ts in self._failures[key] if ts > threshold]
        if valid:
            self._failures[key] = valid
        else:
            self._failures.pop(key, None)
        return valid

    def is_rate_limited(self, key: str) -> bool:
        """Check if a single key has reached or exceeded max failed attempts in window."""
        with self._lock:
            now = datetime.now(UTC).timestamp()
            valid = self._clean_expired(key, now)
            return len(valid) >= self.max_attempts

    def is_any_rate_limited(self, keys: list[str]) -> bool:
        """Check if any of the given keys have reached or exceeded max failed attempts."""
        with self._lock:
            now = datetime.now(UTC).timestamp()
            for key in keys:
                valid = self._clean_expired(key, now)
                if len(valid) >= self.max_attempts:
                    return True
            return False

    def record_failure(self, keys: list[str]) -> None:
        """Record a failed attempt timestamp for each key in keys."""
        with self._lock:
            now = datetime.now(UTC).timestamp()
            for key in keys:
                self._clean_expired(key, now)
                self._failures[key].append(now)

    def reset(self, keys: list[str]) -> None:
        """Reset failure counts for the specified keys upon successful login."""
        with self._lock:
            for key in keys:
                self._failures.pop(key, None)

    def reset_all(self) -> None:
        """Clear all limiter state (used primarily for test isolation)."""
        with self._lock:
            self._failures.clear()


# Module-level shared singleton
login_rate_limiter = LoginRateLimiter()
