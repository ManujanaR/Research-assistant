"""Tests for natural-language query rewriting and chat answering."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import chromadb
import pytest

from app.core.config import get_settings
from app.core.dependencies import (
    get_chat_llm_client,
    get_chroma_client,
    get_embedding_function,
)
from app.main import app
from app.schemas.chat import ChatMessage
from app.services.qa import (
    FALLBACK_GROUNDING_MESSAGE,
    index_document,
)
from app.services.query_rewriter import REWRITE_INSTRUCTION, rewrite_query
from tests.conftest import AuthenticatedTestClient


class FakeStream:
    """Async iterator simulating OpenAI SSE stream."""

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = list(tokens)

    def __aiter__(self) -> AsyncIterator[Any]:
        return self

    async def __anext__(self) -> Any:
        if not self.tokens:
            raise StopAsyncIteration
        token = self.tokens.pop(0)
        return type(
            "Chunk",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {"delta": type("Delta", (), {"content": token})()},
                    )()
                ]
            },
        )()


class RecordingChatClient:
    """Fake OpenAI client that records calls and differentiates rewrite vs stream."""

    def __init__(
        self,
        rewrite_output: str = "rewritten search query",
        stream_tokens: list[str] | None = None,
        rewrite_should_fail: bool = False,
    ) -> None:
        self.rewrite_output = rewrite_output
        self.stream_tokens = (
            stream_tokens
            if stream_tokens is not None
            else ["Answer to original query."]
        )
        self.rewrite_should_fail = rewrite_should_fail
        self.rewrite_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []
        self.chat = type("Chat", (), {"completions": self})()

    async def create(self, **kwargs: Any) -> Any:
        if kwargs.get("stream"):
            self.stream_calls.append(kwargs)
            return FakeStream(self.stream_tokens)

        self.rewrite_calls.append(kwargs)
        if self.rewrite_should_fail:
            raise RuntimeError("Simulated query rewrite API failure")

        return type(
            "Completion",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {
                            "message": type(
                                "Msg", (), {"content": self.rewrite_output}
                            )()
                        },
                    )()
                ]
            },
        )()


class RecordingEmbedder:
    """Deterministic embedder that logs all queries passed to retrieval."""

    def __init__(self, dim: int = 8) -> None:
        self.call_count = 0
        self.queries_received: list[str] = []
        self.dim = dim

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        self.queries_received.extend(texts)
        embeddings: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            lower = text.lower()
            if "deep" in lower or "participant" in lower or "sample" in lower:
                vec[0] = 1.0
            else:
                vec[1] = 1.0
            embeddings.append(vec)
        return embeddings


def parse_sse_events(body: str) -> list[dict[str, Any]]:
    """Parse raw SSE text into event objects."""
    import json

    events = []
    blocks = [b.strip() for b in body.split("\n\n") if b.strip()]
    for block in blocks:
        lines = block.split("\n")
        event_name = None
        data = None
        for line in lines:
            if line.startswith("event: "):
                event_name = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                raw = line[len("data: ") :].strip()
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    data = raw
        if event_name:
            events.append({"event": event_name, "data": data})
    return events


@pytest.mark.asyncio
async def test_rewrite_query_unit_success() -> None:
    """rewrite_query constructs prompt with history turns, temperature 0, and max_tokens 40."""
    fake_client = RecordingChatClient(
        rewrite_output="  'deep neural networks training'  "
    )
    history = [
        ChatMessage(role="user", content="Tell me about neural nets."),
        ChatMessage(role="assistant", content="They are computational models."),
    ]

    result = await rewrite_query(
        question="How were they trained?",
        history=history,
        client=fake_client,
    )

    assert result == "deep neural networks training"
    assert len(fake_client.rewrite_calls) == 1
    call = fake_client.rewrite_calls[0]
    assert call["max_tokens"] == 40
    assert call["temperature"] == 0
    assert call["model"] == get_settings().rewrite_model
    messages = call["messages"]
    assert messages[0]["role"] == "system"
    assert REWRITE_INSTRUCTION in messages[0]["content"]
    assert messages[1]["content"] == "Tell me about neural nets."
    assert messages[2]["content"] == "They are computational models."
    assert messages[3]["content"] == "How were they trained?"


@pytest.mark.asyncio
async def test_rewrite_query_unit_failure_falls_back_to_original(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """When the rewrite LLM call fails, the original question is returned and warning logged without question text."""
    fake_client = RecordingChatClient(rewrite_should_fail=True)
    question = "TopSecretUserQueryDoNotLog12345"

    result = await rewrite_query(
        question=question,
        history=[],
        client=fake_client,
    )

    assert result == question
    # Check that warning was logged
    warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
    assert any("Query rewrite call failed" in r.message for r in warning_records)
    # Crucial: Question text MUST NOT appear anywhere in the logs
    for r in caplog.records:
        assert question not in r.message


def test_followup_question_sends_rewritten_to_retrieval_and_original_to_answer(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """A follow-up question sends rewritten query to retrieval and original question to answer step."""
    doc_hash = "a" * 64
    chroma_dir = tmp_path / "chroma_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[{"text": "Deep neural networks study details.", "page": 1}],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    fake_client = RecordingChatClient(
        rewrite_output="deep neural networks training methodology",
        stream_tokens=["The neural network was trained on GPUs."],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        response = auth_client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": "How was it trained?",
                "history": [
                    {"role": "user", "content": "What architecture is used?"},
                    {"role": "assistant", "content": "A deep neural network."},
                ],
            },
        )
        assert response.status_code == 200

        # 1. Retrieval must receive the rewritten query
        assert "deep neural networks training methodology" in embedder.queries_received
        assert "How was it trained?" not in embedder.queries_received

        # 2. Answer step must receive the ORIGINAL question, NOT the rewritten query
        assert len(fake_client.stream_calls) == 1
        answer_messages = fake_client.stream_calls[0]["messages"]
        user_message_content = answer_messages[-1]["content"]
        assert "Question: How was it trained?" in user_message_content
        assert "deep neural networks training methodology" not in user_message_content

    finally:
        app.dependency_overrides.clear()


def test_rewrite_failure_falls_back_to_original_question(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """A rewrite failure falls back to the original question, and the chat still answers."""
    doc_hash = "b" * 64
    chroma_dir = tmp_path / "chroma_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[{"text": "Deep neural networks study details.", "page": 1}],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    fake_client = RecordingChatClient(
        rewrite_should_fail=True,
        stream_tokens=["Answer despite rewrite failure."],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        response = auth_client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": "deep neural networks study",
                "history": [],
            },
        )
        assert response.status_code == 200
        # When rewrite fails, embedder received the original question
        assert "deep neural networks study" in embedder.queries_received
        events = parse_sse_events(response.text)
        token_events = [e for e in events if e["event"] == "token"]
        assert (
            "".join(e["data"]["text"] for e in token_events)
            == "Answer despite rewrite failure."
        )
    finally:
        app.dependency_overrides.clear()


def test_rewritten_query_never_appears_in_stream_or_user_messages(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """The rewritten query never appears in the streamed answer or in messages sent to the user."""
    doc_hash = "c" * 64
    chroma_dir = tmp_path / "chroma_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[{"text": "Deep learning research paper details.", "page": 1}],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    secret_rewritten_query = "INTERNAL_ACADEMIC_SEARCH_QUERY_XYZ"
    fake_client = RecordingChatClient(
        rewrite_output=secret_rewritten_query,
        stream_tokens=["The study evaluated deep networks."],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        response = auth_client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": "What did they find?",
                "history": [],
            },
        )
        assert response.status_code == 200
        # Rewritten query must not be in the raw SSE output
        assert secret_rewritten_query not in response.text
    finally:
        app.dependency_overrides.clear()


def test_casual_question_retrieves_with_paper_terminology(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """A casual question such as 'how many people took part' retrieves with paper terminology."""
    doc_hash = "d" * 64
    chroma_dir = tmp_path / "chroma_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[{"text": "Participant sample size was 150 volunteers.", "page": 2}],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    fake_client = RecordingChatClient(
        rewrite_output="participant cohort sample size demographics",
        stream_tokens=["A total of 150 volunteers participated in the study."],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        response = auth_client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": "how many people took part",
                "history": [],
            },
        )
        assert response.status_code == 200
        assert (
            "participant cohort sample size demographics" in embedder.queries_received
        )
        assert "how many people took part" not in embedder.queries_received
    finally:
        app.dependency_overrides.clear()


def test_fallback_returned_when_passages_do_not_answer(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """The fallback is still returned when the retrieved passages do not answer the question."""
    doc_hash = "e" * 64
    chroma_dir = tmp_path / "chroma_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[{"text": "Paper on astronomical optics.", "page": 1}],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    fake_client = RecordingChatClient(
        rewrite_output="reinforcement learning policy gradient optimization",
        stream_tokens=[FALLBACK_GROUNDING_MESSAGE],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        response = auth_client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": "What reinforcement learning policy was used?",
                "history": [],
            },
        )
        assert response.status_code == 200
        events = parse_sse_events(response.text)
        token_events = [e for e in events if e["event"] == "token"]
        streamed_answer = "".join(e["data"]["text"] for e in token_events)
        assert streamed_answer == FALLBACK_GROUNDING_MESSAGE

        # Fallback answers MUST send an empty sources list
        sources_events = [e for e in events if e["event"] == "sources"]
        assert len(sources_events) == 1
        assert sources_events[0]["data"] == []
    finally:
        app.dependency_overrides.clear()


def test_greetings_and_small_talk_make_zero_rewrite_and_retrieval_calls(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """Greetings and small talk make zero rewrite calls and zero retrieval calls."""
    doc_hash = "f" * 64
    chroma_dir = tmp_path / "chroma_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[{"text": "Paper on genomics.", "page": 1}],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    fake_client = RecordingChatClient(
        stream_tokens=["Hello! How can I help you with this research paper?"]
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        # Reset embedder after indexing setup so we only record chat retrieval calls
        embedder.call_count = 0
        embedder.queries_received.clear()

        # Test greeting
        response = auth_client.post(
            "/api/chat",
            json={"doc_hash": doc_hash, "message": "hello"},
        )
        assert response.status_code == 200
        assert len(fake_client.rewrite_calls) == 0, (
            "Expected zero rewrite calls for greeting"
        )
        assert embedder.call_count == 0, "Expected zero retrieval calls for greeting"

        # Test small talk / thank you
        response2 = auth_client.post(
            "/api/chat",
            json={"doc_hash": doc_hash, "message": "thank you"},
        )
        assert response2.status_code == 200
        assert len(fake_client.rewrite_calls) == 0, (
            "Expected zero rewrite calls for small talk"
        )
        assert embedder.call_count == 0, "Expected zero retrieval calls for small talk"
    finally:
        app.dependency_overrides.clear()


def test_non_owner_gets_404_before_rewrite_call(
    auth_client_other: AuthenticatedTestClient,
    auth_client: AuthenticatedTestClient,
    tmp_path: Path,
) -> None:
    """A non-owner gets 404 before any rewrite call is made."""
    doc_hash = "0" * 64
    chroma_dir = tmp_path / "chroma_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[{"text": "Paper text.", "page": 1}],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    # Owned by auth_client, NOT auth_client_other
    auth_client.record_ownership(doc_hash)

    # Reset embedder after indexing setup so we only record chat retrieval calls
    embedder.call_count = 0
    embedder.queries_received.clear()

    fake_client = RecordingChatClient(
        rewrite_output="should not be called",
        stream_tokens=["should not run"],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        response = auth_client_other.post(
            "/api/chat",
            json={"doc_hash": doc_hash, "message": "Can you explain it?"},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Document not found. Upload the PDF first."
        assert len(fake_client.rewrite_calls) == 0, (
            "Rewrite must not be called for non-owner"
        )
        assert len(fake_client.stream_calls) == 0, (
            "Stream must not be called for non-owner"
        )
        assert embedder.call_count == 0, "Embedder must not be called for non-owner"
    finally:
        app.dependency_overrides.clear()
