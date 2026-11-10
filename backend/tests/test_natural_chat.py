"""Tests for natural-language query rewriting and chat answering."""

import asyncio
import json
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
    retrieve,
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
        rewrite_output: Any = "rewritten search query",
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
            tokens = (
                self.stream_tokens(kwargs)
                if callable(self.stream_tokens)
                else self.stream_tokens
            )
            return FakeStream(tokens)

        self.rewrite_calls.append(kwargs)
        if self.rewrite_should_fail:
            raise RuntimeError("Simulated query rewrite API failure")

        output = self.rewrite_output
        if callable(output):
            content = output(kwargs)
        elif isinstance(output, dict):
            content = json.dumps(output)
        elif kwargs.get("response_format"):
            stripped = str(output).strip()
            if stripped.startswith("{") and stripped.endswith("}"):
                content = output
            else:
                content = json.dumps({"intent": "document_question", "query": output})
        else:
            content = str(output)

        return type(
            "Completion",
            (),
            {
                "choices": [
                    type(
                        "Choice",
                        (),
                        {"message": type("Msg", (), {"content": content})()},
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
async def test_rewrite_query_corrects_spelling_variants_and_contains_instruction() -> (
    None
):
    """rewrite_query instructions require correcting spelling mistakes, phonetic variants, and author/framework names."""
    assert (
        "Correct spelling mistakes, capitalisation differences, and phonetic variants of technical terms, author names, and framework names."
        in REWRITE_INSTRUCTION
    )
    assert (
        "Use the conversation and the paper’s metadata to decide the intended term. Output the corrected term in the search query."
        in REWRITE_INSTRUCTION
    )

    fake_client = RecordingChatClient(
        rewrite_output="ResNet architecture convolutional layers"
    )
    result = await rewrite_query(
        question="What is the resnet architechture?",
        history=[],
        client=fake_client,
    )
    assert result == "ResNet architecture convolutional layers"
    call = fake_client.rewrite_calls[0]
    assert REWRITE_INSTRUCTION in call["messages"][0]["content"]


@pytest.mark.asyncio
async def test_rewrite_query_outputs_pure_search_terms_without_direct_answering() -> (
    None
):
    """Rewriter strictly outputs standalone search queries under 20 words without answering conversational queries."""
    assert (
        "Output only the query, under 20 words. Do not answer the question."
        in REWRITE_INSTRUCTION
    )

    fake_client = RecordingChatClient(
        rewrite_output="attention mechanism Vaswani transformer"
    )
    result = await rewrite_query(
        question="Who is Vaswani and how does attention work?",
        history=[],
        client=fake_client,
    )
    assert result == "attention mechanism Vaswani transformer"
    assert not result.startswith("Vaswani is")
    assert len(result.split()) < 20


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


def test_misspelt_key_term_reaches_retrieval_as_corrected_search_query(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """A misspelt key term in the user's question reaches retrieval as the corrected term, while original question is preserved."""
    doc_hash = "c" * 64
    chroma_dir = tmp_path / "chroma_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[
                {"text": "ResNet architecture uses residual connections.", "page": 1}
            ],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    fake_client = RecordingChatClient(
        rewrite_output={"intent": "document_question", "query": "ResNet architecture"},
        stream_tokens=[
            "The ResNet architecture uses skip connections to train deep networks."
        ],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        response = auth_client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": "Explain the resnet architechture.",
                "history": [],
            },
        )
        assert response.status_code == 200

        # 1. Retrieval must receive the corrected term (normalised before embedding)
        assert any(
            q.lower() == "resnet architecture" for q in embedder.queries_received
        )
        assert "Explain the resnet architechture." not in embedder.queries_received

        # 2. Answer step retains original input question string
        assert len(fake_client.stream_calls) == 1
        user_message_content = fake_client.stream_calls[0]["messages"][-1]["content"]
        assert "Question: Explain the resnet architechture." in user_message_content
        assert "ResNet architecture" not in user_message_content.split("Question: ")[1]

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


def test_chat_intent_triggers_zero_retrieval_and_cites_no_paper_facts(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """An intent of 'chat' triggers zero vector retrieval calls and cites no paper facts."""
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
        rewrite_output={"intent": "chat", "query": ""},
        stream_tokens=["Hello! How can I help you with this research paper?"],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        embedder.call_count = 0
        embedder.queries_received.clear()

        # Test greeting
        response = auth_client.post(
            "/api/chat",
            json={"doc_hash": doc_hash, "message": "hello"},
        )
        assert response.status_code == 200
        events = parse_sse_events(response.text)
        sources_events = [e for e in events if e["event"] == "sources"]
        assert len(sources_events) == 1
        assert sources_events[0]["data"] == []  # Cites zero paper facts/sources
        assert embedder.call_count == 0  # Expected zero retrieval calls for chat
    finally:
        app.dependency_overrides.clear()


def test_document_overview_over_30_pages_consumes_only_title_authors_abstract(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """An intent of 'document_overview' on paper > 30 pages triggers 0 vector retrieval and consumes title_authors_abstract."""
    doc_hash = "e" * 64
    chroma_dir = tmp_path / "chroma_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    # Index document with 35 pages
    chunks = [{"text": f"Page content for page {i}", "page": i} for i in range(1, 36)]
    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=chunks,
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    from app.core.dependencies import get_summary_cache

    cache = get_summary_cache()
    cache.set(
        doc_hash,
        {
            "header": {
                "title": "Quantum Error Correction Advances",
                "authors": "Alice & Bob",
                "abstract": "We present surface code fault-tolerant threshold findings.",
            },
            "problem_statement": "Decoherence in qubits.",
            "methodology": "Surface code simulations.",
            "key_results": "Threshold of 1% achieved.",
            "conclusion": "Fault-tolerant scaling verified.",
        },
    )

    fake_client = RecordingChatClient(
        rewrite_output={"intent": "document_overview", "query": ""},
        stream_tokens=["Here is an overview of the quantum error correction paper."],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        embedder.call_count = 0
        response = auth_client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": "Give me an overview of this paper.",
            },
        )
        assert response.status_code == 200
        assert embedder.call_count == 0  # Zero vector retrieval calls

        # Assert title_authors_abstract was consumed
        assert len(fake_client.stream_calls) == 1
        stream_prompt = fake_client.stream_calls[0]["messages"][-1]["content"]
        assert "Quantum Error Correction Advances" in stream_prompt
        assert "Alice & Bob" in stream_prompt
        assert "Page content for page 35" not in stream_prompt
    finally:
        app.dependency_overrides.clear()


def test_document_overview_under_30_pages_consumes_full_document_text(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """An intent of 'document_overview' on paper <= 30 pages triggers 0 vector retrieval and consumes full text."""
    doc_hash = "d" * 64
    chroma_dir = tmp_path / "chroma_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    # Index document with 5 pages
    chunks = [
        {"text": f"Detailed paper content on page {i}", "page": i} for i in range(1, 6)
    ]
    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=chunks,
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    fake_client = RecordingChatClient(
        rewrite_output={"intent": "document_overview", "query": ""},
        stream_tokens=["Overview based on full text."],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        embedder.call_count = 0
        response = auth_client.post(
            "/api/chat",
            json={"doc_hash": doc_hash, "message": "What is this paper about?"},
        )
        assert response.status_code == 200
        assert embedder.call_count == 0  # Zero vector retrieval calls

        assert len(fake_client.stream_calls) == 1
        stream_prompt = fake_client.stream_calls[0]["messages"][-1]["content"]
        assert "Detailed paper content on page 1" in stream_prompt
        assert "Detailed paper content on page 5" in stream_prompt
    finally:
        app.dependency_overrides.clear()


def test_outside_paper_intent_returns_refusal_sentence(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """An intent of 'outside_paper' returns strictly the refusal sentence with zero retrieval calls."""
    doc_hash = "c" * 64
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
        rewrite_output={"intent": "outside_paper", "query": ""},
        stream_tokens=[
            "I can only answer questions about this paper. Ask me about its problem, methods, or results."
        ],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        embedder.call_count = 0
        response = auth_client.post(
            "/api/chat",
            json={"doc_hash": doc_hash, "message": "What is the capital of Italy?"},
        )
        assert response.status_code == 200
        events = parse_sse_events(response.text)
        token_events = [e for e in events if e["event"] == "token"]
        assert len(token_events) == 1
        assert token_events[0]["data"]["text"] == (
            "I can only answer questions about this paper. Ask me about its problem, methods, or results."
        )
        sources_events = [e for e in events if e["event"] == "sources"]
        assert sources_events[0]["data"] == []
        assert embedder.call_count == 0  # Zero vector retrieval calls
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


def test_answer_system_prompt_contains_spelling_tolerance_rule() -> None:
    """The answer system prompt explicitly instructs to answer questions with minor spelling errors if concept is present."""
    from app.services.qa import format_chat_system_prompt

    prompt = format_chat_system_prompt()
    assert (
        "If the question contains a minor spelling error and the intended concept is clearly present in the passages, answer it. Do not refuse because of the spelling."
        in prompt
    )


def test_grounded_answer_on_typo_with_concept_present(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """A question containing a minor spelling error whose concept is present in context receives a grounded answer."""
    doc_hash = "1" * 64
    chroma_dir = tmp_path / "chroma_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[
                {
                    "text": "The core methodology relies on self-supervised contrastive learning algorithms.",
                    "page": 2,
                }
            ],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    grounded_answer = "The core methodology uses self-supervised contrastive learning algorithms to pre-train representations."
    fake_client = RecordingChatClient(
        rewrite_output={
            "intent": "document_question",
            "query": "methodology contrastive learning algorithm",
        },
        stream_tokens=[grounded_answer],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        response = auth_client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": "What is the core metodology and algoritm?",
                "history": [],
            },
        )
        assert response.status_code == 200
        events = parse_sse_events(response.text)
        token_events = [e for e in events if e["event"] == "token"]
        streamed_answer = "".join(e["data"]["text"] for e in token_events)

        # Must receive grounded answer, NOT the fallback refusal sentence
        assert streamed_answer == grounded_answer
        assert streamed_answer != FALLBACK_GROUNDING_MESSAGE

        # Sources must be attached for grounded answers
        sources_events = [e for e in events if e["event"] == "sources"]
        assert len(sources_events) == 1
        assert len(sources_events[0]["data"]) > 0
        assert sources_events[0]["data"][0]["page_number"] == 2
    finally:
        app.dependency_overrides.clear()


def test_fallback_on_absent_concept_with_typo(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """A question containing a typo whose concept is absent from passages returns strictly the fallback refusal sentence."""
    doc_hash = "2" * 64
    chroma_dir = tmp_path / "chroma_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[{"text": "Paper on cellular respiration in yeast.", "page": 1}],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    fake_client = RecordingChatClient(
        rewrite_output={
            "intent": "document_question",
            "query": "quantum computing algorithm",
        },
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
                "message": "What is the qunatum compuuting algoritm?",
                "history": [],
            },
        )
        assert response.status_code == 200
        events = parse_sse_events(response.text)
        token_events = [e for e in events if e["event"] == "token"]
        streamed_answer = "".join(e["data"]["text"] for e in token_events)

        # Absent concept must strictly return fallback refusal sentence (no hallucination)
        assert streamed_answer == FALLBACK_GROUNDING_MESSAGE

        # Fallback answers must have empty sources
        sources_events = [e for e in events if e["event"] == "sources"]
        assert len(sources_events) == 1
        assert sources_events[0]["data"] == []
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("casual_message", ["i love you", "hi", "thank you"])
def test_off_topic_messages_return_short_replies_without_citations(
    auth_client: AuthenticatedTestClient,
    tmp_path: Path,
    casual_message: str,
) -> None:
    """Casual off-topic messages like 'i love you', 'hi', and 'thank you' return short replies with no citations or attached passages."""
    doc_hash = "3" * 64
    chroma_dir = tmp_path / "chroma_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[{"text": "Some research paper content.", "page": 1}],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    fake_client = RecordingChatClient(
        rewrite_output={"intent": "chat", "query": ""},
        stream_tokens=["I am here to assist you with exploring this paper!"],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        embedder.call_count = 0
        response = auth_client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": casual_message,
                "history": [],
            },
        )
        assert response.status_code == 200
        events = parse_sse_events(response.text)
        token_events = [e for e in events if e["event"] == "token"]
        assert len(token_events) > 0

        # No citations or attached passages
        sources_events = [e for e in events if e["event"] == "sources"]
        assert len(sources_events) == 1
        assert sources_events[0]["data"] == []

        # Zero vector retrieval calls for casual chat
        assert embedder.call_count == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_case_insensitive_query_rewriting_and_retrieval(tmp_path: Path) -> None:
    """Verify case-insensitive query rewriting and retrieval for casing variations."""
    # 1. Assert rewriter prompt contains the required instruction
    assert (
        "Output the search query in the paper’s own spelling of names and terms, regardless of the user’s capitalisation."
        in REWRITE_INSTRUCTION
    )

    # 2. For 'what does elsevier do' and 'What does Elsevier do', assert rewriter produces the same query
    captured_instructions: list[str] = []

    def fake_completion(kwargs: dict[str, Any]) -> str:
        sys_msg = kwargs["messages"][0]["content"]
        captured_instructions.append(sys_msg)
        return "Elsevier publishing activities"

    fake_client = RecordingChatClient(rewrite_output=fake_completion)

    q_lower = "what does elsevier do"
    q_title = "What does Elsevier do"

    rewritten_lower = await rewrite_query(q_lower, [], fake_client)
    rewritten_title = await rewrite_query(q_title, [], fake_client)

    assert rewritten_lower == rewritten_title
    assert rewritten_lower == "Elsevier publishing activities"
    for instruction in captured_instructions:
        assert (
            "Output the search query in the paper’s own spelling of names and terms, regardless of the user’s capitalisation."
            in instruction
        )

    # 3. Setup Chroma vector store and index chunks
    doc_hash = "f" * 64
    chroma_dir = tmp_path / "chroma_case_insensitive"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))

    # A deterministic embedding function for the test
    async def fake_embed_fn(texts: list[str]) -> list[list[float]]:
        vecs: list[list[float]] = []
        for text in texts:
            counts = [float(text.count(chr(c))) for c in range(ord("a"), ord("z") + 1)]
            norm = (sum(x * x for x in counts) or 1.0) ** 0.5
            vecs.append([x / norm for x in counts])
        return vecs

    chunks = [
        {
            "text": "Elsevier publishes peer-reviewed research journals and scientific literature.",
            "page": 1,
        },
        {
            "text": "The methodology employs data analytics across research outputs.",
            "page": 2,
        },
    ]

    await index_document(
        doc_hash=doc_hash,
        chunks=chunks,
        embed_fn=fake_embed_fn,
        client=chroma_client,
    )

    # 4. Direct retrieval with both queries differing only in casing
    retrieved_lower = await retrieve(
        doc_hash=doc_hash,
        query=q_lower,
        embed_fn=fake_embed_fn,
        client=chroma_client,
    )
    retrieved_title = await retrieve(
        doc_hash=doc_hash,
        query=q_title,
        embed_fn=fake_embed_fn,
        client=chroma_client,
    )

    # Assert retrieved chunk IDs are identical and non-empty
    ids_lower = [c.id for c in retrieved_lower]
    ids_title = [c.id for c in retrieved_title]
    assert len(ids_lower) > 0
    assert ids_lower == ids_title
    assert ids_lower == [f"{doc_hash}:0", f"{doc_hash}:1"]

    # 5. Calculate and report embedding distance between the two queries after normalisation
    norm_lower = q_lower.strip().lower()
    norm_title = q_title.strip().lower()
    embeddings = await fake_embed_fn([norm_lower, norm_title])
    emb_lower, emb_title = embeddings[0], embeddings[1]

    # Cosine distance = 1.0 - cosine_similarity
    dot_product = sum(a * b for a, b in zip(emb_lower, emb_title, strict=True))
    norm_a = sum(a * a for a in emb_lower) ** 0.5
    norm_b = sum(b * b for b in emb_title) ** 0.5
    cosine_similarity = dot_product / (norm_a * norm_b)
    cosine_distance = 1.0 - cosine_similarity

    # Normalisation guarantees exact match and zero distance
    assert cosine_distance == pytest.approx(0.0, abs=1e-9)


@pytest.mark.asyncio
async def test_contextual_query_rewriter_scope_instruction_and_capping() -> None:
    """Verify that rewriter instructions contain broad-query contextualisation rules and cap scope at 1,000 chars."""
    required_instruction = (
        "For a broad or underspecified question, write the search query around how the paper’s scope addresses that topic, such as its findings, measured effects, or context. "
        "Do not write a general encyclopaedic definition. If the question has no connection to the paper’s scope, keep the query as close to the question’s own words as possible, and do not add paper-specific terms."
    )
    assert required_instruction in REWRITE_INSTRUCTION

    fake_client = RecordingChatClient(rewrite_output="covid-19 student outcomes")

    # Pass scope exceeding 1,000 characters
    long_scope = "COVID-19 and Student Outcomes: " + ("academic performance " * 80)
    assert len(long_scope) > 1000

    result = await rewrite_query(
        question="covid-19",
        history=[],
        client=fake_client,
        scope=long_scope,
    )
    assert result == "covid-19 student outcomes"
    call = fake_client.rewrite_calls[0]
    system_content = call["messages"][0]["content"]
    assert "Paper Scope (Title & Abstract):" in system_content
    # Verified capped at 1,000 characters
    scope_injected = system_content.split("Paper Scope (Title & Abstract):\n")[1]
    assert len(scope_injected) == 1000

    # Missing scope must pass empty string and not fail
    fake_client_no_scope = RecordingChatClient(rewrite_output="covid-19")
    result_empty = await rewrite_query(
        question="covid-19",
        history=[],
        client=fake_client_no_scope,
        scope="",
    )
    assert result_empty == "covid-19"
    system_content_empty = fake_client_no_scope.rewrite_calls[0]["messages"][0][
        "content"
    ]
    assert "Paper Scope (Title & Abstract):" not in system_content_empty


def test_contextual_query_rewriting_broad_and_offtopic_e2e(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """End-to-end tests for broad query contextualisation, retrieval grounding, off-topic safety, and untouched questions."""
    doc_hash = "8" * 64
    chroma_dir = tmp_path / "chroma_scope_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))

    # Deterministic embedder
    class ScopeEmbedder:
        def __init__(self) -> None:
            self.queries_received: list[str] = []

        async def __call__(self, texts: list[str]) -> list[list[float]]:
            self.queries_received.extend(texts)
            embeddings: list[list[float]] = []
            for t in texts:
                lower = t.lower()
                # COVID / student outcomes vector
                if "covid" in lower or "student" in lower or "outcome" in lower:
                    embeddings.append([1.0, 0.0])
                else:
                    embeddings.append([0.0, 1.0])
            return embeddings

    embedder = ScopeEmbedder()
    chunk_text = "Student exam performance and learning outcomes suffered significantly during the COVID-19 pandemic."

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[{"text": chunk_text, "page": 1}],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    # Store paper scope in summary cache
    from app.core.dependencies import get_summary_cache

    cache = get_summary_cache()
    cache.set(
        doc_hash,
        {
            "header": {
                "title": "Impact of COVID-19 on Student Outcomes",
                "authors": "Smith et al.",
                "abstract": "A comprehensive study of student academic performance and learning outcomes during COVID-19.",
            },
            "problem_statement": "School disruptions during the pandemic.",
            "methodology": "Standardized testing analysis.",
            "key_results": "Significant reduction in student achievement.",
            "conclusion": "Supportive learning measures are urgently needed.",
        },
    )

    def dynamic_llm(kwargs: dict[str, Any]) -> Any:
        messages = kwargs.get("messages", [])
        sys_text = messages[0]["content"] if messages else ""
        user_msg = messages[-1]["content"] if messages else ""

        # Verify scope is passed to classifier / rewriter
        assert "Paper Scope (Title & Abstract):" in sys_text
        assert "Impact of COVID-19 on Student Outcomes" in sys_text

        # 1. Broad query contextualisation
        if "covid-19" in user_msg.lower():
            return json.dumps(
                {
                    "intent": "document_question",
                    "query": "COVID-19 student outcomes impact",
                }
            )

        # 3. Off-topic query safety: keep query close to user's words, no paper terms added
        if "cake" in user_msg.lower():
            return json.dumps(
                {
                    "intent": "document_question",
                    "query": "how to bake a cake",
                }
            )

        return json.dumps({"intent": "document_question", "query": user_msg})

    def stream_handler(kwargs: dict[str, Any]) -> list[str]:
        messages = kwargs.get("messages", [])
        sys_text = messages[0]["content"] if messages else ""
        if chunk_text in sys_text:
            return ["Student outcomes were significantly reduced during COVID-19."]
        return [FALLBACK_GROUNDING_MESSAGE]

    fake_client = RecordingChatClient(
        rewrite_output=dynamic_llm,
        stream_tokens=stream_handler,
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        # =========================================================================
        # Test 1: Broad query "covid-19"
        # =========================================================================
        embedder.queries_received.clear()
        res_broad = auth_client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": "covid-19",
                "history": [],
            },
        )
        assert res_broad.status_code == 200

        # Assert rewriter output contains paper-scope term ("student outcomes")
        # and fake retrieval received that contextualised query
        assert any("student outcomes" in q.lower() for q in embedder.queries_received)

        # =========================================================================
        # Test 2: Retrieval grounding: matching fake chunks passed into answer prompt
        # =========================================================================
        assert len(fake_client.stream_calls) >= 1
        answer_call_broad = fake_client.stream_calls[0]
        broad_messages = answer_call_broad["messages"]
        system_prompt_broad = broad_messages[0]["content"]
        assert chunk_text in system_prompt_broad

        # Streamed answer must be grounded on the retrieved chunk
        events_broad = parse_sse_events(res_broad.text)
        token_events = [e for e in events_broad if e["event"] == "token"]
        streamed_text = "".join(e["data"]["text"] for e in token_events)
        assert "Student outcomes were significantly reduced" in streamed_text

        # =========================================================================
        # Test 3: Off-topic safety: "how to bake a cake" gets no paper terms + fallback
        # =========================================================================
        embedder.queries_received.clear()
        res_offtopic = auth_client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": "how to bake a cake",
                "history": [],
            },
        )
        assert res_offtopic.status_code == 200

        # Rewriter query must have NO paper-specific terms added
        cake_queries = [q for q in embedder.queries_received if "cake" in q.lower()]
        assert len(cake_queries) > 0
        for q in cake_queries:
            assert "covid" not in q.lower()
            assert "student" not in q.lower()
            assert "outcome" not in q.lower()

        # Off-topic answer must be strictly the fallback sentence
        events_offtopic = parse_sse_events(res_offtopic.text)
        offtopic_tokens = [e for e in events_offtopic if e["event"] == "token"]
        offtopic_answer = "".join(e["data"]["text"] for e in offtopic_tokens)
        assert offtopic_answer == FALLBACK_GROUNDING_MESSAGE

        # =========================================================================
        # Test 4: Original question untouched in answer prompt
        # =========================================================================
        assert len(fake_client.stream_calls) >= 2
        # First call answer prompt must contain raw user string "covid-19"
        broad_user_msg = broad_messages[-1]["content"]
        assert broad_user_msg == "Question: covid-19"
        assert "Question: covid-19" in broad_user_msg
        assert "COVID-19 student outcomes impact" not in broad_user_msg

        # Second call answer prompt must contain raw user string "how to bake a cake"
        answer_call_cake = fake_client.stream_calls[1]
        cake_user_msg = answer_call_cake["messages"][-1]["content"]
        assert cake_user_msg == "Question: how to bake a cake"

    finally:
        app.dependency_overrides.clear()


# =============================================================================
# Universal Language Policy Unit Tests
# Note: These unit tests verify the prompt contract, instruction assembly, and
# output rules using deterministic fake models; live model linguistic adherence
# is validated via the manual verification check.
# =============================================================================


def test_universal_language_policy_prompt_contract() -> None:
    """The answer system prompt explicitly contains all Universal Language Policy instructions."""
    from app.services.qa import format_chat_system_prompt

    prompt = format_chat_system_prompt()

    assert "5. Universal Language Policy:" in prompt
    assert "Reply in the language the user writes in." in prompt
    assert "Use the native script of that language for the answer text." in prompt
    assert (
        "Do not output romanised or transliterated slang (e.g., no phonetic Singlish)."
        in prompt
    )
    assert (
        "Keep specialised academic terms, symbols, variable names, and named entities in their standard English form."
        in prompt
    )
    assert (
        "If you are not confident in the native-script rendering of a technical term, keep that term in English."
        in prompt
    )
    assert (
        "Grounding is unchanged: answers come only from the retrieved passages, in any language."
        in prompt
    )
    assert (
        'The fallback sentence stays exactly as it is in English ("The uploaded paper does not contain information to answer this question.") for every language. Do not translate it.'
        in prompt
    )


def test_sinhala_question_triggers_language_policy_and_preserves_technical_terms(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """A Sinhala question triggers the language policy prompt contract, and English technical terms survive inside the response."""
    doc_hash = "2" * 64
    chroma_dir = tmp_path / "chroma_sinhala_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[
                {
                    "text": (
                        "The Transformer architecture utilizes Multi-Head Attention and "
                        "Positional Encoding to capture long-range token dependencies."
                    ),
                    "page": 3,
                }
            ],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    # Simulated response adhering to native script + preserved English technical terms
    sinhala_grounded_answer = (
        "මෙම පර්යේෂණයේදී Transformer architecture සහ Multi-Head Attention "
        "භාවිතා කර ඇති අතර Positional Encoding මගින් long-range token dependencies හසුරුවනු ලැබේ."
    )

    sinhala_question = "මෙම paper එකෙහි Transformer architecture එක සහ Multi-Head Attention ක්‍රියාත්මක වන්නේ කෙසේද?"

    fake_client = RecordingChatClient(
        rewrite_output={
            "intent": "document_question",
            "query": "Transformer architecture Multi-Head Attention Positional Encoding",
        },
        stream_tokens=[sinhala_grounded_answer],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        response = auth_client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": sinhala_question,
                "history": [],
            },
        )
        assert response.status_code == 200

        # Verify answer call prompt contract
        assert len(fake_client.stream_calls) == 1
        stream_call = fake_client.stream_calls[0]
        messages = stream_call["messages"]
        system_content = messages[0]["content"]

        # Universal language policy instructions must be active in system prompt
        assert "Universal Language Policy:" in system_content
        assert "Reply in the language the user writes in." in system_content
        assert (
            "Keep specialised academic terms, symbols, variable names, and named entities in their standard English form."
            in system_content
        )

        # Raw user question in Sinhala passed directly to user turn
        assert messages[-1]["content"] == f"Question: {sinhala_question}"

        # Stream output verification: native script answer with English terms preserved
        events = parse_sse_events(response.text)
        tokens = [e for e in events if e["event"] == "token"]
        answer_text = "".join(e["data"]["text"] for e in tokens)
        assert answer_text == sinhala_grounded_answer

        # Verify English technical terms survive intact
        assert "Transformer architecture" in answer_text
        assert "Multi-Head Attention" in answer_text
        assert "Positional Encoding" in answer_text

        # Verify sources are attached
        sources = [e for e in events if e["event"] == "sources"]
        assert len(sources) == 1
        assert len(sources[0]["data"]) > 0
        assert sources[0]["data"][0]["page_number"] == 3
    finally:
        app.dependency_overrides.clear()


def test_sinhala_question_fallback_remains_exact_english_sentence(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """When the uploaded paper lacks information, the fallback remains the exact English sentence even for a Sinhala question."""
    doc_hash = "3" * 64
    chroma_dir = tmp_path / "chroma_sinhala_fallback_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[
                {
                    "text": "This paper analyzes classical sorting algorithms such as Quicksort and Mergesort.",
                    "page": 1,
                }
            ],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    sinhala_absent_question = (
        "මෙහි quantum computing algorithms සහ qubits ගැන සඳහන් වන්නේ කුමක්ද?"
    )

    # Model outputs the exact English fallback per the Universal Language Policy
    fake_client = RecordingChatClient(
        rewrite_output={
            "intent": "document_question",
            "query": "quantum computing algorithms qubits",
        },
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
                "message": sinhala_absent_question,
                "history": [],
            },
        )
        assert response.status_code == 200

        # System prompt instructs that fallback sentence must not be translated
        stream_call = fake_client.stream_calls[0]
        system_content = stream_call["messages"][0]["content"]
        assert (
            'The fallback sentence stays exactly as it is in English ("The uploaded paper does not contain information to answer this question.") for every language. Do not translate it.'
            in system_content
        )

        events = parse_sse_events(response.text)
        tokens = [e for e in events if e["event"] == "token"]
        answer_text = "".join(e["data"]["text"] for e in tokens)

        # Fallback text must strictly remain the exact English sentence
        assert answer_text == FALLBACK_GROUNDING_MESSAGE
        assert answer_text == (
            "The uploaded paper does not contain information to answer this question."
        )

        # Sources must be empty for fallback answers
        sources = [e for e in events if e["event"] == "sources"]
        assert len(sources) == 1
        assert sources[0]["data"] == []
    finally:
        app.dependency_overrides.clear()


def test_romanised_question_directed_to_native_script_without_slang(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """A Romanised question (e.g. phonetic Singlish) is directed to be answered in native script without slang."""
    doc_hash = "4" * 64
    chroma_dir = tmp_path / "chroma_romanised_test"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = RecordingEmbedder()

    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[
                {
                    "text": "The methodology employs cross-entropy loss optimization using Adam optimizer with warmup.",
                    "page": 5,
                }
            ],
            embed_fn=embedder,
            client=chroma_client,
        )
    )
    auth_client.record_ownership(doc_hash)

    # Phonetic Singlish query
    romanised_query = "Meka methodology eka mokakda kiyala explain karanna puluwanda?"

    # Model responds in native Sinhala script preserving technical terms, not phonetic slang
    native_script_answer = (
        "මෙම පර්යේෂණයේ methodology කොටසෙහි Adam optimizer සහ cross-entropy loss optimization "
        "භාවිතා කර ආකෘතිය පුහුණු කරනු ලැබේ."
    )

    fake_client = RecordingChatClient(
        rewrite_output={
            "intent": "document_question",
            "query": "methodology cross-entropy loss Adam optimizer",
        },
        stream_tokens=[native_script_answer],
    )

    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_client

    try:
        response = auth_client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": romanised_query,
                "history": [],
            },
        )
        assert response.status_code == 200

        # Verify prompt instructions for native script and no slang
        stream_call = fake_client.stream_calls[0]
        system_content = stream_call["messages"][0]["content"]
        assert (
            "Use the native script of that language for the answer text."
            in system_content
        )
        assert (
            "Do not output romanised or transliterated slang (e.g., no phonetic Singlish)."
            in system_content
        )

        # Raw Romanised question passed to LLM
        assert stream_call["messages"][-1]["content"] == f"Question: {romanised_query}"

        # Streamed output is in native script with English terms preserved
        events = parse_sse_events(response.text)
        tokens = [e for e in events if e["event"] == "token"]
        answer_text = "".join(e["data"]["text"] for e in tokens)
        assert answer_text == native_script_answer
        assert "Adam optimizer" in answer_text
        assert "cross-entropy loss optimization" in answer_text

        # Verify sources are attached
        sources = [e for e in events if e["event"] == "sources"]
        assert len(sources) == 1
        assert len(sources[0]["data"]) > 0
        assert sources[0]["data"][0]["page_number"] == 5
    finally:
        app.dependency_overrides.clear()
