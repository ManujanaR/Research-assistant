"""Tests for document ownership on upload, summary, and chat endpoints."""

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
)
from app.db.session import Base, get_db
from app.main import app
from app.models.document import DocumentOwnership
from app.models.user import User
from app.services.auth_service import hash_password
from app.services.ownership_service import is_owner
from app.services.rate_limiter import login_rate_limiter
from app.services.token_service import create_access_token

VALID_SUMMARY_JSON = json.dumps(
    {
        "title_authors_abstract": "Attention Paper - Vaswani et al.",
        "problem_statement": "Recurrent networks are slow.",
        "methodology": "Transformer with self-attention.",
        "key_results": "State of the art BLEU score.",
        "conclusion": "Attention works efficiently.",
    }
)


# --- Fake LLM helpers to track call counts ---


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


class CallTrackingLLMClient:
    """Mock LLM client that counts calls to summary and chat completions."""

    def __init__(self) -> None:
        self.summary_call_count = 0
        self.chat_call_count = 0
        self.chat = self._Chat(self)

    class _Chat:
        def __init__(self, parent: "CallTrackingLLMClient") -> None:
            self.parent = parent
            self.completions = self._Completions(parent)

        class _Completions:
            def __init__(self, parent: "CallTrackingLLMClient") -> None:
                self.parent = parent

            async def create(self, **kwargs: Any) -> Any:
                if kwargs.get("stream", False):
                    self.parent.chat_call_count += 1
                    return FakeChatStream(["Answer based on paper."])
                self.parent.summary_call_count += 1
                return FakeChatCompletion(
                    choices=[FakeChoice(message=FakeMessage(VALID_SUMMARY_JSON))]
                )


def make_valid_pdf_bytes(text: str = "Research paper test text") -> bytes:
    """Create minimal valid PDF byte string."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), text)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    """Temporary in-memory SQLite database."""
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
def tracking_llm() -> CallTrackingLLMClient:
    """Create a new CallTrackingLLMClient instance."""
    return CallTrackingLLMClient()


@pytest.fixture
def client(
    test_db: Session,
    tmp_path: Path,
    tracking_llm: CallTrackingLLMClient,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[TestClient, None, None]:
    """Configure TestClient with test DB, ephemeral Chroma, and fake LLM."""
    import chromadb

    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-test-key")
    get_settings.cache_clear()

    test_chroma = chromadb.PersistentClient(path=str(tmp_path / ".chroma"))

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[0.1] * 128 for _ in texts]

    def override_get_db() -> Generator[Session, None, None]:
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_chroma_client] = lambda: test_chroma
    app.dependency_overrides[get_embedding_function] = lambda: fake_embed
    app.dependency_overrides[get_llm_client] = lambda: tracking_llm
    app.dependency_overrides[get_chat_llm_client] = lambda: tracking_llm

    login_rate_limiter.reset_all()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    login_rate_limiter.reset_all()
    get_settings.cache_clear()


@pytest.fixture
def users(test_db: Session) -> tuple[User, User]:
    """Create user1 and user2 in the test database."""
    user1 = User(
        email="owner@example.com",
        password_hash=hash_password("OwnerPassword123"),
    )
    user2 = User(
        email="second@example.com",
        password_hash=hash_password("SecondPassword123"),
    )
    test_db.add_all([user1, user2])
    test_db.commit()
    test_db.refresh(user1)
    test_db.refresh(user2)
    return user1, user2


def test_owner_can_upload_summarise_and_chat(
    client: TestClient, users: tuple[User, User]
) -> None:
    """Owner can upload a paper, request its summary, and chat with it."""
    user1, _ = users
    token = create_access_token(user_id=user1.id)
    client.cookies.set("auth_token", token)

    pdf_bytes = make_valid_pdf_bytes("Novel Attention Architecture Experiments")

    # 1. Upload
    upload_resp = client.post(
        "/api/upload",
        files={"file": ("paper.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 200
    doc_hash = upload_resp.json()["doc_hash"]

    # 2. Summary
    summary_resp = client.post("/api/summary", json={"doc_hash": doc_hash})
    assert summary_resp.status_code == 200
    assert (
        summary_resp.json()["title_authors_abstract"]
        == "Attention Paper - Vaswani et al."
    )

    # 3. Chat
    chat_resp = client.post(
        "/api/chat",
        json={"doc_hash": doc_hash, "message": "What is the key result?"},
    )
    assert chat_resp.status_code == 200
    assert "data:" in chat_resp.text


def test_second_user_gets_404_matching_unknown_hash_exactly(
    client: TestClient, users: tuple[User, User]
) -> None:
    """Non-owner gets 404 on summary and chat, matching the unknown hash response exactly."""
    user1, user2 = users

    # User 1 uploads
    client.cookies.set("auth_token", create_access_token(user_id=user1.id))
    pdf_bytes = make_valid_pdf_bytes("Top Secret Research Paper")
    upload_resp = client.post(
        "/api/upload",
        files={"file": ("secret.pdf", pdf_bytes, "application/pdf")},
    )
    doc_hash = upload_resp.json()["doc_hash"]

    # Switch to User 2
    client.cookies.set("auth_token", create_access_token(user_id=user2.id))
    unknown_hash = "a" * 64

    # Summary: compare non-owned doc vs unknown doc
    summary_non_owner = client.post("/api/summary", json={"doc_hash": doc_hash})
    summary_unknown = client.post("/api/summary", json={"doc_hash": unknown_hash})

    assert summary_non_owner.status_code == 404
    assert summary_unknown.status_code == 404
    assert summary_non_owner.json() == summary_unknown.json()
    assert (
        summary_non_owner.json()["detail"]
        == "Document not found. Upload the PDF first."
    )

    # Chat: compare non-owned doc vs unknown doc
    chat_non_owner = client.post(
        "/api/chat",
        json={"doc_hash": doc_hash, "message": "Summarise results"},
    )
    chat_unknown = client.post(
        "/api/chat",
        json={"doc_hash": unknown_hash, "message": "Summarise results"},
    )

    assert chat_non_owner.status_code == 404
    assert chat_unknown.status_code == 404
    assert chat_non_owner.json() == chat_unknown.json()
    assert (
        chat_non_owner.json()["detail"] == "Document not found. Upload the PDF first."
    )


def test_second_user_uploading_same_file_keeps_first_owner(
    client: TestClient, users: tuple[User, User], test_db: Session
) -> None:
    """Uploading the same file by a second user succeeds, but retains original owner."""
    user1, user2 = users
    pdf_bytes = make_valid_pdf_bytes("Common Shared Paper Content")

    # User 1 uploads
    client.cookies.set("auth_token", create_access_token(user_id=user1.id))
    resp1 = client.post(
        "/api/upload",
        files={"file": ("paper.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp1.status_code == 200
    doc_hash = resp1.json()["doc_hash"]

    # User 2 uploads the identical file
    client.cookies.set("auth_token", create_access_token(user_id=user2.id))
    resp2 = client.post(
        "/api/upload",
        files={"file": ("paper.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp2.status_code == 200
    assert resp2.json()["doc_hash"] == doc_hash

    # Ownership remains with user 1 in the database
    ownership = (
        test_db.query(DocumentOwnership)
        .filter(DocumentOwnership.doc_hash == doc_hash)
        .first()
    )
    assert ownership is not None
    assert ownership.owner_id == user1.id
    assert is_owner(doc_hash, user1.id, db=test_db) is True
    assert is_owner(doc_hash, user2.id, db=test_db) is False

    # User 2 cannot access summary or chat
    assert client.post("/api/summary", json={"doc_hash": doc_hash}).status_code == 404
    assert (
        client.post(
            "/api/chat",
            json={"doc_hash": doc_hash, "message": "hello"},
        ).status_code
        == 404
    )

    # User 1 can still access summary
    client.cookies.set("auth_token", create_access_token(user_id=user1.id))
    assert client.post("/api/summary", json={"doc_hash": doc_hash}).status_code == 200


def test_no_auth_gets_401_on_all_three_routes(client: TestClient) -> None:
    """Requests without authentication return 401 on /api/upload, /api/summary, and /api/chat."""
    client.cookies.clear()
    pdf_bytes = make_valid_pdf_bytes("Unauthenticated test payload")
    fake_hash = "f" * 64

    # 1. Upload without auth
    resp_upload = client.post(
        "/api/upload",
        files={"file": ("paper.pdf", pdf_bytes, "application/pdf")},
    )
    assert resp_upload.status_code == 401
    assert resp_upload.json()["detail"] == "Not authenticated"

    # 2. Summary without auth
    resp_summary = client.post("/api/summary", json={"doc_hash": fake_hash})
    assert resp_summary.status_code == 401
    assert resp_summary.json()["detail"] == "Not authenticated"

    # 3. Chat without auth
    resp_chat = client.post(
        "/api/chat",
        json={"doc_hash": fake_hash, "message": "Question?"},
    )
    assert resp_chat.status_code == 401
    assert resp_chat.json()["detail"] == "Not authenticated"


def test_non_owner_makes_zero_llm_calls(
    client: TestClient,
    users: tuple[User, User],
    tracking_llm: CallTrackingLLMClient,
) -> None:
    """Non-owner requests are rejected before any LLM invocations occur."""
    user1, user2 = users

    # User 1 uploads paper
    client.cookies.set("auth_token", create_access_token(user_id=user1.id))
    pdf_bytes = make_valid_pdf_bytes("Zero LLM Call Verification Paper")
    upload_resp = client.post(
        "/api/upload",
        files={"file": ("paper.pdf", pdf_bytes, "application/pdf")},
    )
    doc_hash = upload_resp.json()["doc_hash"]

    # Reset tracking counts
    tracking_llm.summary_call_count = 0
    tracking_llm.chat_call_count = 0

    # User 2 attempts summary
    client.cookies.set("auth_token", create_access_token(user_id=user2.id))
    resp_sum = client.post("/api/summary", json={"doc_hash": doc_hash})
    assert resp_sum.status_code == 404
    assert tracking_llm.summary_call_count == 0

    # User 2 attempts chat
    resp_chat = client.post(
        "/api/chat",
        json={"doc_hash": doc_hash, "message": "Test question"},
    )
    assert resp_chat.status_code == 404
    assert tracking_llm.chat_call_count == 0
