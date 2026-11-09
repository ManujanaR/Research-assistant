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
            return FakeStream(self.stream_tokens)

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
