"""End-to-end integration tests for multi-user authentication, document ownership, and session termination."""

import json
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
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
from app.services.cache import SummaryCache
from app.services.rate_limiter import login_rate_limiter

VALID_SUMMARY_RESPONSE = {
    "header": {
        "title": "Attention Is All You Need",
        "authors": "Vaswani et al.",
        "abstract": "Transformer Architecture and Self-Attention",
    },
    "problem_statement": "Sequential computation in recurrent models limits training parallelization.",
    "methodology": "The Transformer relies entirely on self-attention mechanisms without recurrence.",
    "key_results": "Attains 28.4 BLEU on English-to-German translation task.",
    "conclusion": "Self-attention models train significantly faster and generalize superiorly.",
}


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
    """Async iterator yielding simulated SSE token chunks."""

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = list(tokens)

    def __aiter__(self) -> "FakeChatStream":
        return self

    async def __anext__(self) -> FakeStreamChunk:
        if not self.tokens:
            raise StopAsyncIteration
        return FakeStreamChunk(self.tokens.pop(0))


class FakeLLMClient:
    """Mock LLM client supporting both structured summary completions and streaming chat."""

    def __init__(self, summary_json: str, stream_tokens: list[str]) -> None:
        self.summary_json = summary_json
        self.stream_tokens = list(stream_tokens)
        self.chat = self._Chat(self)

    class _Chat:
        def __init__(self, parent: "FakeLLMClient") -> None:
            self.completions = self._Completions(parent)

        class _Completions:
            def __init__(self, parent: "FakeLLMClient") -> None:
                self.parent = parent

            async def create(self, **kwargs: Any) -> Any:
                if kwargs.get("stream", False):
                    return FakeChatStream(list(self.parent.stream_tokens))
                return FakeChatCompletion(
                    choices=[
                        FakeChoice(
                            message=FakeMessage(content=self.parent.summary_json)
                        )
                    ]
                )


class FakeEmbedder:
    """Deterministic mock embedder returning vectors of dimension 128."""

    def __init__(self, dim: int = 128) -> None:
        self.dim = dim

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            lower = text.lower()
            if "attention" in lower or "transformer" in lower:
                vec[0] = 1.0
            if "methodology" in lower or "results" in lower:
                vec[1] = 1.0
            if not any(vec):
                vec[2] = 0.5
            vectors.append(vec)
        return vectors


def make_pdf_bytes(title: str, topic: str) -> bytes:
    """Generate minimal valid multi-page research paper PDF bytes."""
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text(
        (50, 50),
        f"Title: {title}\n\nAbstract: We present an empirical study on {topic} architectures.",
    )
    p2 = doc.new_page()
    p2.insert_text(
        (50, 50),
        f"Methodology and Results: Detailed findings regarding {topic}.\n"
        "Conclusion: Superior performance demonstrated across benchmarks.",
    )
    data = doc.tobytes()
    doc.close()
    return data


def parse_sse_events(body: str) -> list[dict[str, Any]]:
    """Parse raw SSE body text into structured events."""
    events: list[dict[str, Any]] = []
    blocks = [b.strip() for b in body.split("\n\n") if b.strip()]
    for block in blocks:
        lines = block.split("\n")
        event_name = None
        data = None
        for line in lines:
            if line.startswith("event: "):
                event_name = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                try:
                    data = json.loads(line[len("data: ") :].strip())
                except json.JSONDecodeError:
                    data = line[len("data: ") :].strip()
        if event_name is not None:
            events.append({"event": event_name, "data": data})
    return events


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    """In-memory SQLite database with StaticPool so all client connections share the DB."""
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
def auth_env(
    test_db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None, None, None]:
    """Set up dependencies: database, isolated Chroma, cache, and fake LLM/embedder."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-e2e-auth-key")
    monkeypatch.setenv("AUTH_SECRET_KEY", "super-secret-auth-key-32-bytes-long")
    get_settings.cache_clear()

    chroma_client = chromadb.PersistentClient(path=str(tmp_path / ".chroma"))
    summary_cache = SummaryCache(cache_dir=tmp_path / "summaries")
    fake_embedder = FakeEmbedder()
    fake_llm = FakeLLMClient(
        summary_json=json.dumps(VALID_SUMMARY_RESPONSE),
        stream_tokens=["The ", "Transformer ", "achieves ", "state of the art BLEU."],
    )

    def override_get_db() -> Generator[Session, None, None]:
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: fake_embedder
    app.dependency_overrides[get_summary_cache] = lambda: summary_cache
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_llm

    login_rate_limiter.reset_all()

    yield

    app.dependency_overrides.clear()
    login_rate_limiter.reset_all()
    get_settings.cache_clear()


def test_full_flow_across_two_users_isolation_and_signout(auth_env: None) -> None:
    """E2E flow: User A signs up, uploads, summarises, and chats.

    User B signs up, and is denied access (404) to User A's document on summary and chat.
    Signing out terminates User A's session.
    """
    client_a = TestClient(app)
    client_b = TestClient(app)

    # 1. Sign up as User A
    signup_a_resp = client_a.post(
        "/api/auth/signup",
        json={"email": "usera@example.com", "password": "PasswordUserA123"},
    )
    assert signup_a_resp.status_code == 201
    user_a_info = signup_a_resp.json()
    assert user_a_info["email"] == "usera@example.com"
    assert "id" in user_a_info

    # Sign in as User A
    signin_a_resp = client_a.post(
        "/api/auth/signin",
        json={"email": "usera@example.com", "password": "PasswordUserA123"},
    )
    assert signin_a_resp.status_code == 200
    assert "auth_token" in client_a.cookies

    # Verify session via /api/auth/me
    me_a_resp = client_a.get("/api/auth/me")
    assert me_a_resp.status_code == 200
    assert me_a_resp.json()["email"] == "usera@example.com"

    # 2. User A uploads a research paper
    pdf_bytes_a = make_pdf_bytes("Attention Mechanisms", "Transformer Self-Attention")
    upload_a_resp = client_a.post(
        "/api/upload",
        files={"file": ("attention_paper_a.pdf", pdf_bytes_a, "application/pdf")},
    )
    assert upload_a_resp.status_code == 200
    upload_a_data = upload_a_resp.json()
    doc_hash_a = upload_a_data["doc_hash"]
    assert len(doc_hash_a) == 64
    assert upload_a_data["page_count"] == 2

    # 3. User A summarises their document
    summary_a_resp = client_a.post("/api/summary", json={"doc_hash": doc_hash_a})
    assert summary_a_resp.status_code == 200
    summary_a_data = summary_a_resp.json()
    assert "header" in summary_a_data
    assert "problem_statement" in summary_a_data
    assert "methodology" in summary_a_data
    assert "key_results" in summary_a_data
    assert "conclusion" in summary_a_data

    # 4. User A chats about their document
    chat_a_resp = client_a.post(
        "/api/chat",
        json={
            "doc_hash": doc_hash_a,
            "message": "What are the key results of the study?",
            "history": [],
        },
    )
    assert chat_a_resp.status_code == 200
    assert "text/event-stream" in chat_a_resp.headers.get("content-type", "")
    events_a = parse_sse_events(chat_a_resp.text)
    event_names_a = [e["event"] for e in events_a]
    assert "done" in event_names_a
    assert "token" in event_names_a

    # 5. Sign up and sign in as User B
    signup_b_resp = client_b.post(
        "/api/auth/signup",
        json={"email": "userb@example.com", "password": "PasswordUserB456"},
    )
    assert signup_b_resp.status_code == 201
    user_b_info = signup_b_resp.json()
    assert user_b_info["email"] == "userb@example.com"
    assert user_b_info["id"] != user_a_info["id"]

    signin_b_resp = client_b.post(
        "/api/auth/signin",
        json={"email": "userb@example.com", "password": "PasswordUserB456"},
    )
    assert signin_b_resp.status_code == 200
    assert "auth_token" in client_b.cookies

    me_b_resp = client_b.get("/api/auth/me")
    assert me_b_resp.status_code == 200
    assert me_b_resp.json()["email"] == "userb@example.com"

    # 6. Confirm User B gets 404 for User A's document on summary
    b_summary_resp = client_b.post("/api/summary", json={"doc_hash": doc_hash_a})
    assert b_summary_resp.status_code == 404
    assert (
        b_summary_resp.json()["detail"] == "Document not found. Upload the PDF first."
    )

    # 7. Confirm User B gets 404 for User A's document on chat
    b_chat_resp = client_b.post(
        "/api/chat",
        json={
            "doc_hash": doc_hash_a,
            "message": "Can I read User A's findings?",
            "history": [],
        },
    )
    assert b_chat_resp.status_code == 404
    assert b_chat_resp.json()["detail"] == "Document not found. Upload the PDF first."

    # 8. Confirm sign-out ends User A's session
    signout_a_resp = client_a.post("/api/auth/signout")
    assert signout_a_resp.status_code == 200
    assert signout_a_resp.json() == {"status": "ok"}

    # After sign-out, /api/auth/me returns 401
    me_a_after = client_a.get("/api/auth/me")
    assert me_a_after.status_code == 401
    assert "Not authenticated" in me_a_after.json()["detail"]

    # Protected endpoints return 401 for User A
    assert (
        client_a.post("/api/summary", json={"doc_hash": doc_hash_a}).status_code == 401
    )
    assert (
        client_a.post(
            "/api/chat",
            json={"doc_hash": doc_hash_a, "message": "Test", "history": []},
        ).status_code
        == 401
    )
    assert (
        client_a.post(
            "/api/upload",
            files={"file": ("another.pdf", pdf_bytes_a, "application/pdf")},
        ).status_code
        == 401
    )

    # 9. Confirm User B's session remains unaffected and can upload and access their own document
    pdf_bytes_b = make_pdf_bytes("Graph Neural Networks", "Message Passing Algorithms")
    upload_b_resp = client_b.post(
        "/api/upload",
        files={"file": ("graph_paper_b.pdf", pdf_bytes_b, "application/pdf")},
    )
    assert upload_b_resp.status_code == 200
    doc_hash_b = upload_b_resp.json()["doc_hash"]
    assert doc_hash_b != doc_hash_a

    summary_b_resp = client_b.post("/api/summary", json={"doc_hash": doc_hash_b})
    assert summary_b_resp.status_code == 200

    chat_b_resp = client_b.post(
        "/api/chat",
        json={
            "doc_hash": doc_hash_b,
            "message": "What are the graph findings?",
            "history": [],
        },
    )
    assert chat_b_resp.status_code == 200


def test_user_b_uploading_identical_document_does_not_steal_ownership(
    auth_env: None,
) -> None:
    """A second user uploading the identical PDF file receives the hash but cannot access the document."""
    client_a = TestClient(app)
    client_b = TestClient(app)

    # User A registers and signs in
    client_a.post(
        "/api/auth/signup",
        json={"email": "alpha@example.com", "password": "Password123Alpha"},
    )
    client_a.post(
        "/api/auth/signin",
        json={"email": "alpha@example.com", "password": "Password123Alpha"},
    )

    # User B registers and signs in
    client_b.post(
        "/api/auth/signup",
        json={"email": "beta@example.com", "password": "Password123Beta"},
    )
    client_b.post(
        "/api/auth/signin",
        json={"email": "beta@example.com", "password": "Password123Beta"},
    )

    # User A uploads a paper
    pdf_bytes = make_pdf_bytes("Shared Paper Title", "Transformer Attention")
    upload_a = client_a.post(
        "/api/upload",
        files={"file": ("shared_paper.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_a.status_code == 200
    doc_hash = upload_a.json()["doc_hash"]

    # User B uploads the exact same paper
    upload_b = client_b.post(
        "/api/upload",
        files={"file": ("shared_paper.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_b.status_code == 200
    assert upload_b.json()["doc_hash"] == doc_hash

    # User A still owns the document
    assert client_a.post("/api/summary", json={"doc_hash": doc_hash}).status_code == 200
    assert (
        client_a.post(
            "/api/chat",
            json={"doc_hash": doc_hash, "message": "Summary question", "history": []},
        ).status_code
        == 200
    )

    # User B cannot access User A's document despite having uploaded the same bytes
    b_sum = client_b.post("/api/summary", json={"doc_hash": doc_hash})
    assert b_sum.status_code == 404
    assert b_sum.json()["detail"] == "Document not found. Upload the PDF first."

    b_chat = client_b.post(
        "/api/chat",
        json={"doc_hash": doc_hash, "message": "Can I query this?", "history": []},
    )
    assert b_chat.status_code == 404
    assert b_chat.json()["detail"] == "Document not found. Upload the PDF first."


def test_unauthenticated_requests_fail_on_all_protected_endpoints(
    auth_env: None,
) -> None:
    """Calls without valid auth cookie receive HTTP 401 across all protected routes."""
    anon_client = TestClient(app)
    fake_hash = "a" * 64

    # 1. /api/auth/me
    assert anon_client.get("/api/auth/me").status_code == 401

    # 2. /api/upload
    pdf_bytes = make_pdf_bytes("Test Title", "Test Topic")
    upload_resp = anon_client.post(
        "/api/upload",
        files={"file": ("test.pdf", pdf_bytes, "application/pdf")},
    )
    assert upload_resp.status_code == 401

    # 3. /api/summary
    assert (
        anon_client.post("/api/summary", json={"doc_hash": fake_hash}).status_code
        == 401
    )

    # 4. /api/chat
    assert (
        anon_client.post(
            "/api/chat",
            json={"doc_hash": fake_hash, "message": "Hello", "history": []},
        ).status_code
        == 401
    )
