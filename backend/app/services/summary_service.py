from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from chromadb.api import ClientAPI


class PaperTextStore(Protocol):
    """Protocol for accessing stored raw paper text by document hash."""

    def get_text(self, doc_hash: str) -> str | None:
        """Retrieve stored extracted text for a document hash, or None if not found."""
        ...

    def set_text(self, doc_hash: str, text: str) -> None:
        """Store extracted text for a document hash."""
        ...


class InMemoryPaperTextStore:
    """Process-wide in-memory implementation of PaperTextStore with Chroma rehydration fallback."""

    def __init__(self, chroma_client: "ClientAPI | None" = None) -> None:
        self._store: dict[str, str] = {}
        self.chroma_client = chroma_client

    def get_text(self, doc_hash: str) -> str | None:
        """Retrieve stored extracted text for a document hash.

        Checks memory first; on a miss, rehydrates from Chroma and caches in memory.
        """
        if doc_hash in self._store:
            return self._store[doc_hash]

        from app.services.qa import rebuild_text_from_chroma

        rebuilt = rebuild_text_from_chroma(doc_hash, client=self.chroma_client)
        if rebuilt is not None:
            self._store[doc_hash] = rebuilt
            return rebuilt

        return None

    def set_text(self, doc_hash: str, text: str) -> None:
        """Store extracted text for a document hash."""
        self._store[doc_hash] = text

    def clear(self) -> None:
        """Clear all stored document texts."""
        self._store.clear()
