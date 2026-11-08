import logging
from typing import Any

from app.core.config import get_settings
from app.schemas.chat import ChatMessage

logger = logging.getLogger(__name__)

REWRITE_INSTRUCTION = (
    "Rewrite the user’s latest message as a standalone search query for finding passages in the paper. "
    "Resolve pronouns such as ‘it’, ‘the first one’, and ‘that’ using the conversation. "
    "Expand casual wording into the technical terms a research paper would use. "
    "Output only the query, under 20 words. Do not answer the question."
)


async def rewrite_query(
    question: str,
    history: list[ChatMessage],
    client: Any,
) -> str:
    """Rewrite conversational or follow-up question into a standalone academic search query.

    Uses REWRITE_MODEL with the last REWRITE_HISTORY_TURNS turns of conversation history.
    Falls back gracefully to the original question on any failure without exposing question text in logs.
    """
    settings = get_settings()

    try:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": REWRITE_INSTRUCTION}
        ]

        turns = max(1, int(settings.rewrite_history_turns))
        max_messages = turns * 2
        recent_history = history[-max_messages:] if history else []

        for msg in recent_history:
            messages.append({"role": msg.role, "content": msg.content})

        messages.append({"role": "user", "content": question})

        response = await client.chat.completions.create(
            model=settings.rewrite_model,
            messages=messages,
            max_tokens=40,
            temperature=0,
        )

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

        rewritten = raw_content.strip().strip('"').strip("'").strip()
        if not rewritten:
            return question

        return rewritten
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Query rewrite call failed (%s); falling back to original question.",
            type(exc).__name__,
        )
        return question
