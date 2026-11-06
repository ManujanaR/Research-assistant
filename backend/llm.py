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
