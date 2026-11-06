from typing import Protocol


class PaperTextStore(Protocol):
    """Protocol for accessing stored raw paper text by document hash."""

    def get_text(self, doc_hash: str) -> str | None:
        """Retrieve stored extracted text for a document hash, or None if not found."""
        ...

    def set_text(self, doc_hash: str, text: str) -> None:
        """Store extracted text for a document hash."""
        ...


class InMemoryPaperTextStore:
    """Process-wide in-memory implementation of PaperTextStore."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get_text(self, doc_hash: str) -> str | None:
        """Retrieve stored extracted text for a document hash, or None if not found."""
        return self._store.get(doc_hash)

    def set_text(self, doc_hash: str, text: str) -> None:
        """Store extracted text for a document hash."""
        self._store[doc_hash] = text

    def clear(self) -> None:
        """Clear all stored document texts."""
        self._store.clear()
