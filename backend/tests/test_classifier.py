"""Unit tests for single structured classifier and query rewriter."""

import asyncio
import json
from typing import Any

import pytest

from app.schemas.chat import ChatMessage
from app.services.classifier import (
    ClassifierResult,
    classify_and_rewrite,
)


class FakeClassifierClient:
    """Mock OpenAI client for classifier unit tests."""

    def __init__(
        self,
        response_content: str | None = None,
        delay_seconds: float = 0.0,
        should_raise: Exception | None = None,
    ) -> None:
        self.response_content = (
            response_content
            or '{"intent": "document_question", "query": "rewritten query"}'
        )
        self.delay_seconds = delay_seconds
        self.should_raise = should_raise
        self.calls: list[dict[str, Any]] = []
        self.chat = type("Chat", (), {"completions": self})()

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        if self.should_raise is not None:
            raise self.should_raise

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
                                "Msg", (), {"content": self.response_content}
                            )()
                        },
                    )()
                ]
            },
        )()


@pytest.mark.asyncio
async def test_mixed_message_routes_to_document_question() -> None:
    """Verify mixed message (conversational filler + question) routes to document_question with query."""
    expected_response = {
        "intent": "document_question",
        "query": "sample size methodology",
    }
    client = FakeClassifierClient(response_content=json.dumps(expected_response))

    result = await classify_and_rewrite(
        message="thanks, and what about the sample?",
        history=[],
        client=client,
    )

    assert isinstance(result, ClassifierResult)
    assert result.intent == "document_question"
    assert result.query == "sample size methodology"
    assert len(client.calls) == 1
    assert client.calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_classifier_timeout_safely_defaults_to_document_question(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A classifier timeout (> 4.0s) safely defaults to document_question using raw text and logs warning without text."""
    client = FakeClassifierClient(delay_seconds=4.5)
    secret_question = "SensitiveRawUserQuestion12345"

    result = await classify_and_rewrite(
        message=secret_question,
        history=[],
        client=client,
        timeout_seconds=0.1,  # Shortened for rapid test execution
    )

    assert result.intent == "document_question"
    assert result.query == secret_question

    # Privacy check: log warning must omit user message text
    warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any("Chat classifier call failed" in w for w in warnings)
    for record in caplog.records:
        assert secret_question not in record.message


@pytest.mark.asyncio
async def test_malformed_invalid_json_safely_defaults_to_document_question(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Malformed or schema-violating JSON from the classifier safely defaults to document_question."""
    client = FakeClassifierClient(response_content="This is not JSON at all {broken}")
    question = "What is the primary conclusion?"

    result = await classify_and_rewrite(
        message=question,
        history=[],
        client=client,
    )

    assert result.intent == "document_question"
    assert result.query == question

    warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any("Chat classifier call failed" in w for w in warnings)
    for record in caplog.records:
        assert question not in record.message


@pytest.mark.asyncio
async def test_unknown_intent_in_json_safely_defaults_to_document_question() -> None:
    """Invalid intent value defaults safely to document_question."""
    client = FakeClassifierClient(
        response_content=json.dumps(
            {"intent": "unsupported_type", "query": "something"}
        )
    )
    question = "Can you clarify the results?"

    result = await classify_and_rewrite(
        message=question,
        history=[],
        client=client,
    )

    assert result.intent == "document_question"
    assert result.query == question


@pytest.mark.asyncio
async def test_pure_chat_classification_empties_query() -> None:
    """Pure chat intent returns query as empty string even if model returned text."""
    client = FakeClassifierClient(
        response_content=json.dumps({"intent": "chat", "query": "hello query"})
    )

    result = await classify_and_rewrite(
        message="Hello! Good morning.",
        history=[],
        client=client,
    )

    assert result.intent == "chat"
    assert result.query == ""


@pytest.mark.asyncio
async def test_document_overview_classification_empties_query() -> None:
    """Document overview intent returns query as empty string."""
    client = FakeClassifierClient(
        response_content=json.dumps(
            {"intent": "document_overview", "query": "overview of paper"}
        )
    )

    result = await classify_and_rewrite(
        message="Give me an overview of the paper.",
        history=[],
        client=client,
    )

    assert result.intent == "document_overview"
    assert result.query == ""


@pytest.mark.asyncio
async def test_outside_paper_classification_empties_query() -> None:
    """Outside paper intent returns query as empty string."""
    client = FakeClassifierClient(
        response_content=json.dumps(
            {"intent": "outside_paper", "query": "weather forecast"}
        )
    )

    result = await classify_and_rewrite(
        message="What is the weather in Tokyo?",
        history=[],
        client=client,
    )

    assert result.intent == "outside_paper"
    assert result.query == ""


@pytest.mark.asyncio
async def test_history_strictly_passes_last_3_turns() -> None:
    """Only the last 3 conversation turns (up to 6 messages) are passed to the classifier."""
    history = [
        ChatMessage(role="user", content="Turn 1 user"),
        ChatMessage(role="assistant", content="Turn 1 assistant"),
        ChatMessage(role="user", content="Turn 2 user"),
        ChatMessage(role="assistant", content="Turn 2 assistant"),
        ChatMessage(role="user", content="Turn 3 user"),
        ChatMessage(role="assistant", content="Turn 3 assistant"),
        ChatMessage(role="user", content="Turn 4 user"),
        ChatMessage(role="assistant", content="Turn 4 assistant"),
        ChatMessage(role="user", content="Turn 5 user"),
        ChatMessage(role="assistant", content="Turn 5 assistant"),
    ]

    client = FakeClassifierClient()
    await classify_and_rewrite(
        message="Turn 6 user question",
        history=history,
        client=client,
    )

    assert len(client.calls) == 1
    messages = client.calls[0]["messages"]

    # 1 system message + 6 history messages + 1 current user message = 8 messages
    assert len(messages) == 8
    assert messages[0]["role"] == "system"
    assert messages[1]["content"] == "Turn 3 user"
    assert messages[2]["content"] == "Turn 3 assistant"
    assert messages[3]["content"] == "Turn 4 user"
    assert messages[4]["content"] == "Turn 4 assistant"
    assert messages[5]["content"] == "Turn 5 user"
    assert messages[6]["content"] == "Turn 5 assistant"
    assert messages[7]["content"] == "Turn 6 user question"


@pytest.mark.asyncio
async def test_default_values_apply_when_model_omits_fields() -> None:
    """When the model omits is_comparative and comparison_targets, safe defaults apply."""
    client = FakeClassifierClient(
        response_content=json.dumps(
            {"intent": "document_question", "query": "standard question"}
        )
    )

    result = await classify_and_rewrite(
        message="What is the dataset?",
        history=[],
        client=client,
    )

    assert result.intent == "document_question"
    assert result.query == "standard question"
    assert result.is_comparative is False
    assert result.comparison_targets == []


@pytest.mark.asyncio
async def test_valid_comparative_response_parses_both_fields() -> None:
    """A valid comparative response parses is_comparative and comparison_targets correctly."""
    client = FakeClassifierClient(
        response_content=json.dumps(
            {
                "intent": "document_question",
                "query": "compare abstract against results",
                "is_comparative": True,
                "comparison_targets": ["abstract", "results"],
            }
        )
    )

    result = await classify_and_rewrite(
        message="Does the abstract match the results?",
        history=[],
        client=client,
    )

    assert result.intent == "document_question"
    assert result.query == "compare abstract against results"
    assert result.is_comparative is True
    assert result.comparison_targets == ["abstract", "results"]


@pytest.mark.asyncio
async def test_malformed_comparative_fields_safely_default_without_raising() -> None:
    """Malformed or wrong-typed comparative fields fall back safely to defaults without raising."""
    client = FakeClassifierClient(
        response_content=json.dumps(
            {
                "intent": "document_question",
                "query": "valid query text",
                "is_comparative": "not_a_bool",
                "comparison_targets": {"not": "a_list"},
            }
        )
    )

    result = await classify_and_rewrite(
        message="Compare abstract with findings",
        history=[],
        client=client,
    )

    assert result.intent == "document_question"
    assert result.query == "valid query text"
    assert result.is_comparative is False
    assert result.comparison_targets == []


@pytest.mark.asyncio
async def test_intent_and_query_parse_identically_with_new_fields() -> None:
    """Non-document_question intents clear query and comparative fields exactly as before."""
    client = FakeClassifierClient(
        response_content=json.dumps(
            {
                "intent": "chat",
                "query": "extraneous query",
                "is_comparative": True,
                "comparison_targets": ["abstract"],
            }
        )
    )

    result = await classify_and_rewrite(
        message="Thank you so much!",
        history=[],
        client=client,
    )

    assert result.intent == "chat"
    assert result.query == ""
    assert result.is_comparative is False
    assert result.comparison_targets == []
