"""Tests for metadata injection into Chat QA with strict grounding boundaries."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.chat import ChatMessage
from app.services.qa import (
    FALLBACK_GROUNDING_MESSAGE,
    RetrievedChunk,
    assemble_chat_messages,
    format_chat_system_prompt,
    stream_chat_response,
)


class FakeStreamChunk:
    def __init__(self, token: str) -> None:
        self.choices = [MagicMock(delta=MagicMock(content=token))]


class FakeStream:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = list(tokens)

    def __aiter__(self) -> "FakeStream":
        return self

    async def __anext__(self) -> FakeStreamChunk:
        if not self.tokens:
            raise StopAsyncIteration
        return FakeStreamChunk(self.tokens.pop(0))


def test_metadata_system_prompt_formatting() -> None:
    """System prompt correctly formats metadata block and strict grounding boundaries."""
    meta = {
        "title": "Attention Is All You Need",
        "authors": "Vaswani et al.",
        "detected_publisher": "NeurIPS",
        "detected_venue": "Conference on Neural Information Processing Systems",
        "publication_year": 2017,
    }
    prompt = format_chat_system_prompt(meta)
    assert "<DOCUMENT_METADATA>" in prompt
    assert "Publisher: NeurIPS" in prompt
    assert "Venue: Conference on Neural Information Processing Systems" in prompt
    assert "Publication Year: 2017" in prompt
    assert "Strict Grounding Boundaries" in prompt
    assert (
        "The <DOCUMENT_METADATA> block may be used SOLELY to answer factual queries about publisher, venue, publication year, title, or authors"
        in prompt
    )
    assert (
        "All queries regarding methodology, results, data, scientific claims, experiments, or analysis MUST be answered strictly from retrieved passages in <PAPER_EXCERPTS>"
        in prompt
    )


def test_assemble_chat_messages_includes_metadata_and_excerpts() -> None:
    """assemble_chat_messages injects metadata and excerpts into prompt structure."""
    chunks = [
        RetrievedChunk(
            text="We use 8 attention heads in the transformer encoder.",
            page=3,
            distance=0.2,
        )
    ]
    meta = {
        "detected_publisher": "IEEE",
        "detected_venue": "CVPR",
        "publication_year": 2021,
    }
    messages = assemble_chat_messages(
        question="Who is the publisher?",
        history=[],
        chunks=chunks,
        metadata=meta,
    )

    system_msg = messages[0]["content"]
    user_msg = messages[1]["content"]

    assert "Publisher: IEEE" in system_msg
    assert "[Page 3]" in user_msg
    assert "We use 8 attention heads" in user_msg
    assert "Question: Who is the publisher?" in user_msg


@pytest.mark.asyncio
async def test_query_publisher_answers_correctly_from_metadata() -> None:
    """Case 1: Query 'Who is the publisher?' answers correctly using detected_publisher."""
    meta = {
        "title": "Deep Residual Learning",
        "authors": "He et al.",
        "detected_publisher": "IEEE",
        "detected_venue": "CVPR",
        "publication_year": 2016,
    }
    chunks = [
        RetrievedChunk(
            text="Residual connections prevent degradation in very deep networks.",
            page=1,
            distance=0.3,
        )
    ]

    messages = assemble_chat_messages(
        question="Who is the publisher?",
        history=[],
        chunks=chunks,
        metadata=meta,
    )

    mock_client = MagicMock()
    # Model generates answer using metadata
    mock_client.chat.completions.create = AsyncMock(
        return_value=FakeStream(["The publisher is IEEE."])
    )

    tokens = []
    async for chunk_str in stream_chat_response(
        messages, sources=[], client=mock_client, question="Who is the publisher?"
    ):
        if chunk_str.startswith("event: token\n"):
            data = json.loads(chunk_str.split("data: ")[1])
            tokens.append(data.get("text", ""))

    full_answer = "".join(tokens)
    assert "IEEE" in full_answer


@pytest.mark.asyncio
async def test_query_methodology_grounds_strictly_in_retrieved_chunks() -> None:
    """Case 2: Query 'What methodology was used?' grounds answer strictly in retrieved chunks without deriving from metadata."""
    meta = {
        "title": "Deep Residual Learning",
        "authors": "He et al.",
        "detected_publisher": "IEEE",
        "detected_venue": "CVPR",
        "publication_year": 2016,
    }
    chunks = [
        RetrievedChunk(
            text="Methodology: We evaluate deep residual networks with shortcut connections and batch normalization.",
            page=2,
            distance=0.15,
        )
    ]

    messages = assemble_chat_messages(
        question="What methodology was used?",
        history=[
            ChatMessage(role="user", content="Who is the publisher?"),
            ChatMessage(role="assistant", content="The publisher is IEEE."),
        ],
        chunks=chunks,
        metadata=meta,
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=FakeStream(
            [
                "The authors used deep residual networks with shortcut connections and batch normalization."
            ]
        )
    )

    tokens = []
    async for chunk_str in stream_chat_response(
        messages, sources=[], client=mock_client, question="What methodology was used?"
    ):
        if chunk_str.startswith("event: token\n"):
            data = json.loads(chunk_str.split("data: ")[1])
            tokens.append(data.get("text", ""))

    full_answer = "".join(tokens)
    assert "shortcut connections" in full_answer
    assert "batch normalization" in full_answer


@pytest.mark.asyncio
async def test_unsupported_query_returns_exact_standard_refusal() -> None:
    """Case 3: Unsupported query neither in chunks nor in metadata returns exact standard refusal sentence."""
    meta = {
        "title": "Deep Residual Learning",
        "authors": "He et al.",
        "detected_publisher": "IEEE",
        "detected_venue": "CVPR",
        "publication_year": 2016,
    }
    chunks = [
        RetrievedChunk(
            text="Methodology: We evaluate deep residual networks with shortcut connections.",
            page=2,
            distance=0.15,
        )
    ]

    messages = assemble_chat_messages(
        question="What was the learning rate schedule?",
        history=[],
        chunks=chunks,
        metadata=meta,
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=FakeStream([FALLBACK_GROUNDING_MESSAGE])
    )

    tokens = []
    async for chunk_str in stream_chat_response(
        messages,
        sources=[],
        client=mock_client,
        question="What was the learning rate schedule?",
    ):
        if chunk_str.startswith("event: token\n"):
            data = json.loads(chunk_str.split("data: ")[1])
            tokens.append(data.get("text", ""))

    full_answer = "".join(tokens)
    assert full_answer == FALLBACK_GROUNDING_MESSAGE
