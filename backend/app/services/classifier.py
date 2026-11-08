import asyncio
import json
import logging
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.schemas.chat import ChatMessage

logger = logging.getLogger(__name__)

IntentType = Literal["chat", "document_overview", "document_question", "outside_paper"]
CLASSIFIER_TIMEOUT_SECONDS: float = 4.0

CLASSIFIER_SYSTEM_PROMPT = """You are a request classifier and query rewriter for an academic research assistant.
Analyze the user's latest message in the context of the conversation and classify its intent into exactly one of:
1. "chat": Conversational pleasantries, greetings, small talk, gratitude, or polite remarks without any question about the paper.
2. "document_overview": Requests for a high-level summary, overview, main findings, core idea, or general topic of the uploaded paper.
3. "document_question": Specific questions about the uploaded paper's content, problem statement, methodology, experiments, results, citations, or data.
4. "outside_paper": Questions completely unrelated to the research paper or document analysis (e.g. general trivia, weather, unrelated coding or writing requests).

Rules:
- Mixed Messages: Any message containing both conversational filler and a question (e.g., "thanks, and what about the sample?") MUST be classified as "document_question".
- Query Rewriting:
  * If the intent is "document_question", the "query" field MUST contain a standalone search query (under 20 words) for retrieving relevant passages from the paper. Resolve pronouns (such as "it", "that", "the first one") using the conversation history, and expand casual wording into technical academic terms.
  * If the intent is NOT "document_question", the "query" field MUST be strictly an empty string ("").

Output strictly a JSON object conforming to:
{
  "intent": "chat" | "document_overview" | "document_question" | "outside_paper",
  "query": string
}"""


class ClassifierResult(BaseModel):
    """Structured result of intent classification and semantic query rewriting."""

    intent: IntentType = Field(default="document_question")
    query: str = Field(default="")


async def classify_and_rewrite(
    message: str,
    history: list[ChatMessage],
    client: Any,
    timeout_seconds: float = CLASSIFIER_TIMEOUT_SECONDS,
) -> ClassifierResult:
    """Classify user message intent and rewrite search query in a single structured call.

    Uses REWRITE_MODEL with strictly the last 3 conversation turns (up to 6 messages).
    Times out after timeout_seconds (default 4.0s) and fails safely to:
    {"intent": "document_question", "query": "<raw_user_message>"}
    without logging the user message text for privacy.
    """
    settings = get_settings()

    try:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT}
        ]

        # Strictly the last 3 conversation turns (up to 6 messages: user + assistant)
        recent_history = history[-6:] if history else []
        for msg in recent_history:
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": message})

        coro = client.chat.completions.create(
            model=settings.rewrite_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=60,
        )

        response = await asyncio.wait_for(coro, timeout=timeout_seconds)

        raw_content = ""
        if hasattr(response, "choices") and response.choices:
            msg_obj = response.choices[0].message
            if hasattr(msg_obj, "content"):
                raw_content = msg_obj.content or ""
            elif isinstance(msg_obj, dict):
                raw_content = msg_obj.get("content", "") or ""
        elif isinstance(response, dict):
            choices = response.get("choices", [])
            if choices:
                msg_obj = choices[0].get("message", {})
                raw_content = msg_obj.get("content", "") or ""

        parsed = json.loads(raw_content)
        result = ClassifierResult.model_validate(parsed)

        if result.intent != "document_question":
            result.query = ""
        elif not result.query.strip():
            result.query = message

        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Chat classifier call failed (%s); defaulting to document_question with raw query.",
            type(exc).__name__,
        )
        return ClassifierResult(intent="document_question", query=message)
