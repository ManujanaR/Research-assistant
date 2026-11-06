import json
import os
from typing import Any
from google import genai
from google.genai import types
from google.genai.errors import APIError


def call_gemini_json(prompt: str) -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
    client = genai.Client(api_key=api_key)

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
    except APIError as err:
        raise RuntimeError(f"Gemini API error: {str(err)}") from err

    raw_text = (response.text or "").strip()
    if raw_text.startswith("```json"):
        raw_text = raw_text[7:]
    elif raw_text.startswith("```"):
        raw_text = raw_text[3:]
    if raw_text.endswith("```"):
        raw_text = raw_text[:-3]

    try:
        parsed = json.loads(raw_text.strip())
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError as err:
        raise RuntimeError(f"Failed to parse LLM JSON output: {str(err)}") from err


def embed_texts(texts: list[str], batch_size: int = 50) -> list[list[float]]:
    if not texts:
        return []

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")

    embed_model = os.environ.get(
        "GEMINI_EMBED_MODEL", "text-embedding-004"
    ).strip()
    client = genai.Client(api_key=api_key)

    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        try:
            res = client.models.embed_content(
                model=embed_model,
                contents=batch,
            )
        except APIError as err:
            raise RuntimeError(f"Gemini Embed API error: {str(err)}") from err

        if not res.embeddings:
            raise RuntimeError("Gemini Embed API returned empty embeddings.")

        for emb in res.embeddings:
            all_embeddings.append(emb.values or [])

    return all_embeddings


def answer_question(
    question: str, context_chunks: list[dict[str, Any]]
) -> str:
    if not context_chunks:
        return "Not found in paper"

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set.")

    model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
    client = genai.Client(api_key=api_key)

    context_str = "\n\n".join(
        f"[Section: {c.get('section', 'Unknown')}, Page: {c.get('page', 'Unknown')}]\n{c.get('text', '')}"
        for c in context_chunks
    )

    prompt = (
        "You are an assistant answering questions about a research paper.\n"
        "Answer the question using ONLY the context provided below. "
        "Cite the section and page number for each claim you make (e.g. [Section ..., Page ...]). "
        "If the provided context does not contain the answer, reply exactly with: Not found in paper\n\n"
        f"Context:\n{context_str}\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
        )
    except APIError as err:
        raise RuntimeError(f"Gemini API error: {str(err)}") from err

    ans = (response.text or "").strip()
    return ans if ans else "Not found in paper"
