import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.dependencies import (
    get_chat_llm_client,
    get_chroma_client,
    get_embedding_function,
    get_llm_client,
    get_summary_cache,
)
from app.main import app
from app.services.cache import SummaryCache

client = TestClient(app)

VALID_SUMMARY_RESPONSE = {
    "title_authors_abstract": "Attention Is All You Need - Vaswani et al. - Transformer Architecture",
    "problem_statement": "Sequential computation in recurrent models limits parallelization during training.",
    "methodology": "The Transformer network architecture relies entirely on self-attention mechanisms without recurrence.",
    "key_results": "Attains 28.4 BLEU on English-to-German and 41.8 BLEU on English-to-French translation.",
    "conclusion": "Self-attention models train significantly faster and generalize well across multiple tasks.",
}


# --- Scripted Fakes for End-to-End Testing ---


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
    """Async iterator of streaming SSE chunks."""

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = list(tokens)

    def __aiter__(self) -> "FakeChatStream":
        return self

    async def __anext__(self) -> FakeStreamChunk:
        if not self.tokens:
            raise StopAsyncIteration
        return FakeStreamChunk(self.tokens.pop(0))


class DualFakeCompletions:
    """Fake completions handler supporting both structured output and streaming."""

    def __init__(self, summary_json: str, stream_tokens: list[str]) -> None:
        self.summary_json = summary_json
        self.stream_tokens = list(stream_tokens)
        self.call_count = 0

    async def create(self, **kwargs: Any) -> Any:
        self.call_count += 1
        if kwargs.get("stream"):
            return FakeChatStream(tokens=self.stream_tokens)
        return FakeChatCompletion(
            choices=[FakeChoice(message=FakeMessage(content=self.summary_json))]
        )


class FakeLLMClient:
    """Fake OpenAI client recording calls for E2E tests."""

    def __init__(self, summary_json: str, stream_tokens: list[str]) -> None:
        self.completions = DualFakeCompletions(summary_json, stream_tokens)
        self.chat = type("Chat", (), {"completions": self.completions})()

    @property
    def call_count(self) -> int:
        return self.completions.call_count


class CountingEmbedder:
    """Deterministic embedding function recording call counts."""

    def __init__(self, dim: int = 8) -> None:
        self.call_count = 0
        self.dim = dim

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        embeddings: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            lower = text.lower()
            if "attention" in lower or "transformer" in lower:
                vec[0] = 1.0
            if "evaluation" in lower or "translation" in lower:
                vec[1] = 1.0
            if not any(vec):
                vec[2] = 1.0
            embeddings.append(vec)
        return embeddings


def parse_sse_events(body: str) -> list[dict[str, Any]]:
    """Parse raw SSE body into list of event dicts."""
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
                data = json.loads(line[len("data: ") :].strip())
        if event_name is not None:
            events.append({"event": event_name, "data": data})
    return events


def generate_two_page_pdf_bytes() -> bytes:
    """Generate a clean two-page research paper PDF using PyMuPDF."""
    doc = pymupdf.open()

    page1 = doc.new_page()
    page1.insert_text(
        (50, 50),
        "Title: Attention Is All You Need\n\n"
        "Abstract: The dominant sequence transduction models are based on complex "
        "recurrent or convolutional neural networks. We propose the Transformer, "
        "a model architecture eschewing recurrence and entirely relying on an "
        "attention mechanism to draw global dependencies between input and output.",
    )

    page2 = doc.new_page()
    page2.insert_text(
        (50, 50),
        "Methodology and Results:\n\n"
        "The Transformer allows for significantly more parallelization and can reach "
        "a new state of the art in translation quality. On the WMT 2014 English-to-German "
        "translation task, the big transformer model establishes a new state-of-the-art BLEU score.",
    )

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.mark.asyncio
async def test_full_e2e_flow_upload_summary_chat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end smoke test: upload 2-page PDF, generate summary, and stream chat answers with citations."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-e2e-key")
    get_settings.cache_clear()

    # Isolated ChromaDB and SummaryCache directories
    chroma_dir = tmp_path / "e2e_chroma"
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    summary_cache = SummaryCache(cache_dir=tmp_path / "e2e_summaries")

    embedder = CountingEmbedder()
    fake_llm = FakeLLMClient(
        summary_json=json.dumps(VALID_SUMMARY_RESPONSE),
        stream_tokens=["The Transformer ", "model achieves ", "state of the art BLEU."],
    )

    # Patch dependencies
    app.dependency_overrides[get_chroma_client] = lambda: chroma_client
    app.dependency_overrides[get_embedding_function] = lambda: embedder
    app.dependency_overrides[get_summary_cache] = lambda: summary_cache
    app.dependency_overrides[get_llm_client] = lambda: fake_llm
    app.dependency_overrides[get_chat_llm_client] = lambda: fake_llm

    try:
        # Step 1: Upload two-page PDF to /api/upload
        pdf_bytes = generate_two_page_pdf_bytes()
        upload_resp = client.post(
            "/api/upload",
            files={"file": ("attention_paper.pdf", pdf_bytes, "application/pdf")},
        )
        assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
        upload_data = upload_resp.json()

        doc_hash = upload_data["doc_hash"]
        assert len(doc_hash) == 64
        assert upload_data["filename"] == "attention_paper.pdf"
        assert upload_data["page_count"] == 2
        assert upload_data["chunk_count"] >= 2

        # Step 2: Request structured summary from /api/summary
        summary_resp = client.post("/api/summary", json={"doc_hash": doc_hash})
        assert summary_resp.status_code == 200, f"Summary failed: {summary_resp.text}"
        summary_data = summary_resp.json()

        expected_keys = [
            "title_authors_abstract",
            "problem_statement",
            "methodology",
            "key_results",
            "conclusion",
        ]
        for key in expected_keys:
            assert key in summary_data
            assert len(summary_data[key]) > 0

        # Step 3: Stream grounded chat answer from /api/chat
        chat_resp = client.post(
            "/api/chat",
            json={
                "doc_hash": doc_hash,
                "message": "What translation quality did the model achieve?",
                "history": [],
            },
        )
        assert chat_resp.status_code == 200, f"Chat failed: {chat_resp.text}"
        assert chat_resp.headers["content-type"].startswith("text/event-stream")

        events = parse_sse_events(chat_resp.text)
        assert len(events) >= 3

        token_events = [e for e in events if e["event"] == "token"]
        source_events = [e for e in events if e["event"] == "sources"]
        done_events = [e for e in events if e["event"] == "done"]

        assert len(token_events) >= 1
        assert len(source_events) == 1
        assert len(done_events) == 1

        # Check sequence: token events, then exactly one sources event, then one done event
        assert events[-1]["event"] == "done"
        assert events[-2]["event"] == "sources"

        streamed_answer = "".join(e["data"]["text"] for e in token_events)
        assert "BLEU" in streamed_answer

        sources = source_events[0]["data"]
        assert isinstance(sources, list)
        assert len(sources) >= 1
        assert sources[0]["page_number"] in [1, 2]
        assert len(sources[0]["snippet"]) <= 200

        # Step 4: Verify fake clients were called and no mock missed
        assert embedder.call_count >= 2, (
            "Embedder must be called for indexing and retrieval"
        )
        assert fake_llm.call_count >= 2, (
            "LLM must be called for summary and chat streaming"
        )

    finally:
        app.dependency_overrides.clear()
