"""Tests for deduplicated storage with isolated per-account access and chat."""

import json
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.core.dependencies import (
    get_chat_llm_client,
    get_chroma_client,
    get_embedding_function,
    get_llm_client,
    get_summary_cache,
)
from app.db.session import Base, get_db
from app.main import app
from app.models.document import DocumentOwnership
from app.models.user import User
from app.services.auth_service import hash_password
from app.services.cache import SummaryCache
from app.services.ownership_service import is_owner
from app.services.rate_limiter import login_rate_limiter
from app.services.token_service import create_access_token

VALID_SUMMARY_JSON = json.dumps(
    {
        "header": {
            "title": "Deduplication in Neural Storage",
            "authors": "Alice & Bob",
            "abstract": "We explore deduplication without sharing access.",
        },
        "problem_statement": "Storage redundancy on identical document uploads.",
        "methodology": "Content-addressed storage with per-account ownership records.",
        "key_results": "Zero redundant embeddings with full multi-tenant isolation.",
        "conclusion": "Per-account ownership provides complete privacy with deduplicated storage.",
    }
)


@dataclass
class FakeMessage:
    content: str


@dataclass
class FakeChoice:
    message: FakeMessage


@dataclass
class FakeChatCompletion:
    choices: list[FakeChoice]


class FakeDelta:
    def __init__(self, content: str | None) -> None:
        self.content = content


class FakeStreamChoice:
    def __init__(self, delta: FakeDelta) -> None:
        self.delta = delta


class FakeStreamChunk:
    def __init__(self, content: str | None) -> None:
        self.choices = [FakeStreamChoice(FakeDelta(content))]


class FakeChatStream:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = list(tokens)

    def __aiter__(self) -> "FakeChatStream":
        return self

    async def __anext__(self) -> FakeStreamChunk:
        if not self.tokens:
            raise StopAsyncIteration
        return FakeStreamChunk(self.tokens.pop(0))


class TrackingLLMClient:
    """Mock LLM client tracking summary, chat, and classifier call counts and payloads."""

    def __init__(self) -> None:
        self.summary_call_count = 0
        self.chat_call_count = 0
        self.classifier_call_count = 0
        self.captured_chat_messages: list[list[dict[str, Any]]] = []
        self.chat = self._Chat(self)
        self.beta = self._Beta(self)

    class _Chat:
        def __init__(self, parent: "TrackingLLMClient") -> None:
            self.parent = parent
            self.completions = self._Completions(parent)

        class _Completions:
            def __init__(self, parent: "TrackingLLMClient") -> None:
                self.parent = parent

            async def create(self, **kwargs: Any) -> Any:
                messages = kwargs.get("messages", [])
                if kwargs.get("stream", False):
                    self.parent.chat_call_count += 1
                    self.parent.captured_chat_messages.append(messages)
                    return FakeChatStream(["Answer strictly from the uploaded paper."])

                # Check if it's classifier / query rewriter or summarizer
                self.parent.summary_call_count += 1
                return FakeChatCompletion(
                    choices=[FakeChoice(message=FakeMessage(VALID_SUMMARY_JSON))]
                )

    class _Beta:
        def __init__(self, parent: "TrackingLLMClient") -> None:
            self.chat = self._BetaChat(parent)

        class _BetaChat:
            def __init__(self, parent: "TrackingLLMClient") -> None:
                self.completions = self._BetaCompletions(parent)

            class _BetaCompletions:
                def __init__(self, parent: "TrackingLLMClient") -> None:
                    self.parent = parent

                async def parse(self, **kwargs: Any) -> Any:
                    self.parent.classifier_call_count += 1
                    response_format = kwargs.get("response_format")
                    if response_format is not None:
                        # Return classification result for chat classifier
                        from unittest.mock import MagicMock

                        res = MagicMock()
                        res.intent = "document_question"
                        res.query = "standalone research query"
                        fake_parsed_choice = MagicMock()
                        fake_parsed_choice.parsed = res
                        return MagicMock(choices=[fake_parsed_choice])

                    return FakeChatCompletion(
                        choices=[FakeChoice(message=FakeMessage(VALID_SUMMARY_JSON))]
                    )


class TrackingEmbeddingFunction:
    """Mock embedding function tracking call counts and embedded text counts."""

    def __init__(self) -> None:
        self.call_count = 0
        self.total_texts_embedded = 0

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        self.total_texts_embedded += len(texts)
        return [[0.05] * 128 for _ in texts]


def make_pdf_bytes(title: str, body: str) -> bytes:
    """Create minimal test PDF document bytes."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), f"{title}\n\n{body}\n\nConclusion section.")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    """Temporary in-memory SQLite database with composite PK support."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def tracking_llm() -> TrackingLLMClient:
    return TrackingLLMClient()


@pytest.fixture
def tracking_embed() -> TrackingEmbeddingFunction:
    return TrackingEmbeddingFunction()


@pytest.fixture
def client_env(
    test_db: Session,
    tmp_path: Path,
    tracking_llm: TrackingLLMClient,
    tracking_embed: TrackingEmbeddingFunction,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, SummaryCache], None, None]:
    """Configure TestClient with test DB, ephemeral Chroma, cache, and fakes."""
    from unittest.mock import patch

    import chromadb

    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-duplicate-test-key")
    get_settings.cache_clear()

    test_chroma = chromadb.PersistentClient(path=str(tmp_path / ".chroma"))
    test_cache = SummaryCache(cache_dir=tmp_path / "summary_cache")

    def override_get_db() -> Generator[Session, None, None]:
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_chroma_client] = lambda: test_chroma
    app.dependency_overrides[get_embedding_function] = lambda: tracking_embed
    app.dependency_overrides[get_llm_client] = lambda: tracking_llm
    app.dependency_overrides[get_chat_llm_client] = lambda: tracking_llm
    app.dependency_overrides[get_summary_cache] = lambda: test_cache

    login_rate_limiter.reset_all()

    async def fake_credibility(*args: Any, **kwargs: Any) -> None:
        return None

    with (
        patch("app.api.upload.evaluate_document_credibility", fake_credibility),
        TestClient(app) as test_client,
    ):
        yield test_client, test_cache

    app.dependency_overrides.clear()
    login_rate_limiter.reset_all()
    get_settings.cache_clear()


@pytest.fixture
def users_abc(test_db: Session) -> tuple[User, User, User]:
    """Create three test users: User A, User B, and User C."""
    user_a = User(
        email="user_a@example.com",
        password_hash=hash_password("Password123A"),
    )
    user_b = User(
        email="user_b@example.com",
        password_hash=hash_password("Password123B"),
    )
    user_c = User(
        email="user_c@example.com",
        password_hash=hash_password("Password123C"),
    )
    test_db.add_all([user_a, user_b, user_c])
    test_db.commit()
    test_db.refresh(user_a)
    test_db.refresh(user_b)
    test_db.refresh(user_c)
    return user_a, user_b, user_c


def test_duplicate_upload_deduplication_and_isolation(
    client_env: tuple[TestClient, SummaryCache],
    users_abc: tuple[User, User, User],
    test_db: Session,
    tracking_llm: TrackingLLMClient,
    tracking_embed: TrackingEmbeddingFunction,
) -> None:
    """Verify deduplicated storage, skipped re-embedding, skipped re-summarising,

    scoped reads, unknown-doc 404 for non-uploaders, and isolated chat histories.
    """
    client, _ = client_env
    user_a, user_b, user_c = users_abc
    pdf_bytes = make_pdf_bytes(
        "Attention Mechanisms", "Transformers scale with attention."
    )

    # -------------------------------------------------------------------------
    # 1. User A uploads paper.pdf
    # -------------------------------------------------------------------------
    client.cookies.set("auth_token", create_access_token(user_id=user_a.id))
    upload_resp_a = client.post(
        "/api/upload",
        files={"file": ("paper.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp_a.status_code == 200
    data_a = upload_resp_a.json()
    doc_hash = data_a["doc_hash"]

    # Verify response shape
    expected_keys = {
        "doc_hash",
        "filename",
        "size_bytes",
        "page_count",
        "chunk_count",
        "ocr_used",
    }
    assert set(data_a.keys()) == expected_keys
    assert data_a["page_count"] >= 1
    assert data_a["chunk_count"] >= 1

    # Ownership row exists for User A only
    ownership_rows_after_a = (
        test_db.query(DocumentOwnership)
        .filter(DocumentOwnership.doc_hash == doc_hash)
        .all()
    )
    assert len(ownership_rows_after_a) == 1
    assert ownership_rows_after_a[0].owner_id == user_a.id
    assert is_owner(doc_hash, user_a.id, db=test_db) is True
    assert is_owner(doc_hash, user_b.id, db=test_db) is False
    assert is_owner(doc_hash, user_c.id, db=test_db) is False

    # User A requests summary -> summary resolves for A
    sum_resp_a = client.post("/api/summary", json={"doc_hash": doc_hash})
    assert sum_resp_a.status_code == 200
    assert sum_resp_a.json()["header"]["title"] == "Deduplication in Neural Storage"
    assert tracking_llm.summary_call_count == 1

    # Record baseline call counts
    embed_calls_after_a = tracking_embed.call_count
    assert embed_calls_after_a > 0  # Re-embedding was performed for User A

    # -------------------------------------------------------------------------
    # 2. User B uploads identical bytes
    # -------------------------------------------------------------------------
    client.cookies.set("auth_token", create_access_token(user_id=user_b.id))
    upload_resp_b = client.post(
        "/api/upload",
        files={"file": ("paper.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp_b.status_code == 200
    data_b = upload_resp_b.json()

    # The response shape matches a new upload
    assert set(data_b.keys()) == expected_keys
    assert data_b["doc_hash"] == doc_hash
    assert data_b["page_count"] == data_a["page_count"]
    assert data_b["chunk_count"] == data_a["chunk_count"]
    assert data_b["size_bytes"] == data_a["size_bytes"]
    assert data_b["ocr_used"] == data_a["ocr_used"]

    # NO re-embedding: embed call count must not increase
    assert tracking_embed.call_count == embed_calls_after_a

    # B gets an ownership row for B only
    ownership_rows_after_b = (
        test_db.query(DocumentOwnership)
        .filter(DocumentOwnership.doc_hash == doc_hash)
        .all()
    )
    assert len(ownership_rows_after_b) == 2
    owner_ids = {row.owner_id for row in ownership_rows_after_b}
    assert owner_ids == {user_a.id, user_b.id}
    assert is_owner(doc_hash, user_b.id, db=test_db) is True
    assert is_owner(doc_hash, user_a.id, db=test_db) is True
    assert is_owner(doc_hash, user_c.id, db=test_db) is False

    # -------------------------------------------------------------------------
    # 3. User B's summary and chat return 200 for B (with NO re-summarising)
    # -------------------------------------------------------------------------
    summary_calls_before_b = tracking_llm.summary_call_count
    sum_resp_b = client.post("/api/summary", json={"doc_hash": doc_hash})
    assert sum_resp_b.status_code == 200
    assert sum_resp_b.json() == sum_resp_a.json()

    # NO re-summarising: summary call count must not increase (cached summary reused)
    assert tracking_llm.summary_call_count == summary_calls_before_b

    # User B chat returns 200
    chat_resp_b = client.post(
        "/api/chat",
        json={
            "doc_hash": doc_hash,
            "message": "What is the key takeaway?",
            "history": [],
        },
    )
    assert chat_resp_b.status_code == 200
    assert "event: token" in chat_resp_b.text

    # -------------------------------------------------------------------------
    # 4. User C, who uploaded nothing, gets 404 byte-identical to unknown hash
    # -------------------------------------------------------------------------
    client.cookies.set("auth_token", create_access_token(user_id=user_c.id))
    unknown_hash = "0" * 64

    # Summary 404 comparison
    c_summary_resp = client.post("/api/summary", json={"doc_hash": doc_hash})
    unknown_summary_resp = client.post("/api/summary", json={"doc_hash": unknown_hash})
    assert c_summary_resp.status_code == 404
    assert unknown_summary_resp.status_code == 404
    assert c_summary_resp.content == unknown_summary_resp.content
    assert c_summary_resp.json() == {
        "detail": "Document not found. Upload the PDF first."
    }

    # Chat 404 comparison
    c_chat_resp = client.post(
        "/api/chat",
        json={"doc_hash": doc_hash, "message": "Can I see this?", "history": []},
    )
    unknown_chat_resp = client.post(
        "/api/chat",
        json={"doc_hash": unknown_hash, "message": "Can I see this?", "history": []},
    )
    assert c_chat_resp.status_code == 404
    assert unknown_chat_resp.status_code == 404
    assert c_chat_resp.content == unknown_chat_resp.content
    assert c_chat_resp.json() == {"detail": "Document not found. Upload the PDF first."}

    # -------------------------------------------------------------------------
    # 5. A's and B's chat histories are separate per account
    # -------------------------------------------------------------------------
    tracking_llm.captured_chat_messages.clear()

    # User A chats with their own history
    client.cookies.set("auth_token", create_access_token(user_id=user_a.id))
    history_a = [
        {"role": "user", "content": "Question from User A"},
        {"role": "assistant", "content": "Answer for User A"},
    ]
    resp_chat_a = client.post(
        "/api/chat",
        json={
            "doc_hash": doc_hash,
            "message": "Follow-up question from User A",
            "history": history_a,
        },
    )
    assert resp_chat_a.status_code == 200

    # User B chats with their own distinct history
    client.cookies.set("auth_token", create_access_token(user_id=user_b.id))
    history_b = [
        {"role": "user", "content": "Unique question from User B"},
        {"role": "assistant", "content": "Unique answer for User B"},
    ]
    resp_chat_b = client.post(
        "/api/chat",
        json={
            "doc_hash": doc_hash,
            "message": "Second unique question from User B",
            "history": history_b,
        },
    )
    assert resp_chat_b.status_code == 200

    # Inspect the captured LLM messages for each call:
    # Call 1 (User A) must contain User A's history and not User B's
    assert len(tracking_llm.captured_chat_messages) >= 2
    captured_a = json.dumps(tracking_llm.captured_chat_messages[0])
    captured_b = json.dumps(tracking_llm.captured_chat_messages[1])

    assert "Question from User A" in captured_a
    assert "Unique question from User B" not in captured_a

    # Call 2 (User B) must contain User B's history and not User A's
    assert "Unique question from User B" in captured_b
    assert "Question from User A" not in captured_b
