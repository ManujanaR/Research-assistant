from typing import Any

try:
    from llm import call_gemini_json
except ImportError:
    from backend.llm import call_gemini_json

SUMMARY_KEYS = (
    "title_authors_abstract",
    "problem_statement",
    "methodology",
    "key_results",
    "conclusion",
)

SUMMARY_PROMPT = """You are a research paper assistant. Analyze the paper text below and produce a structured summary.
Your response MUST be a JSON object with exactly these five keys:
1. "title_authors_abstract": The paper title, authors, and concise abstract.
2. "problem_statement": The core problem or question the paper addresses.
3. "methodology": The proposed approach, architecture, or techniques.
4. "key_results": The primary findings, experimental metrics, and outcomes.
5. "conclusion": The conclusions and main takeaways.

Rules:
- Base every summary value strictly on the paper text.
- If a section or information is missing from the text, provide "Not found in paper" for that key.

Paper text:
{text}
"""


def summarize_paper(text: str) -> dict[str, str]:
    if not text.strip():
        return {key: "Not found in paper" for key in SUMMARY_KEYS}

    trimmed = text[:60000]
    prompt = SUMMARY_PROMPT.format(text=trimmed)
    raw: dict[str, Any] = call_gemini_json(prompt)

    summary: dict[str, str] = {}
    for key in SUMMARY_KEYS:
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            summary[key] = val.strip()
        else:
            summary[key] = "Not found in paper"

    return summary
