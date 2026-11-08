"""Metadata extraction and persistence service for research papers."""

import asyncio
import json
import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.document import DocumentMetadata

logger = logging.getLogger(__name__)

HEADER_EXTRACTION_SYSTEM_PROMPT = """You are a metadata extraction assistant for academic research papers.
Analyze ONLY the provided Page 1 header block text and extract:
1. "detected_publisher": The publishing organization, society, or publisher name (e.g. IEEE, ACM, Springer, Elsevier, Nature, etc.), or null if none is explicitly mentioned.
2. "detected_venue": The publication conference, journal, or workshop name, or null if none is explicitly mentioned.
3. "publication_year": The 4-digit publication year strictly if an explicit 4-digit year is present within the provided header block. Otherwise, null.

Rules:
- DO NOT invent or infer publishers, venues, or years. If not explicitly found in the header text, return null.
- Extract publication_year ONLY from the provided Page 1 header block. Exclude years from body paragraphs, footnotes, or references.
- DO NOT use hardcoded keyword lists or static publisher arrays.
- Return strictly a JSON object conforming to:
{
  "detected_publisher": string | null,
  "detected_venue": string | null,
  "publication_year": integer | null
}"""


class HeaderMetadata(BaseModel):
    """Structured publication metadata dynamically extracted from Page 1 header."""

    detected_publisher: str | None = Field(default=None)
    detected_venue: str | None = Field(default=None)
    publication_year: int | None = Field(default=None)


async def extract_header_metadata(
    header_text: str,
    client: Any = None,
    timeout_seconds: float = 4.0,
) -> HeaderMetadata:
    """Extract publisher, venue, and publication year dynamically from Page 1 header block.

    Privacy & Grounding Guarantee:
    - Receives STRICTLY the isolated Page 1 header text (never the document body or references).
    - Excludes years appearing in body paragraphs, footnotes, or reference entries.
    - Fails safely to all nulls on timeout, network error, or invalid JSON without failing the upload.
    """
    if not header_text or not header_text.strip():
        return HeaderMetadata()

    settings = get_settings()
    if client is None:
        from app.core.dependencies import get_chat_llm_client

        client = get_chat_llm_client()

    try:
        messages = [
            {"role": "system", "content": HEADER_EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"<PAGE_1_HEADER>\n{header_text.strip()}\n</PAGE_1_HEADER>",
            },
        ]

        coro = client.chat.completions.create(
            model=settings.rewrite_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=80,
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
        pub_year = parsed.get("publication_year")
        if pub_year is not None:
            try:
                pub_year = int(pub_year)
                # Year Guard: must be 4-digit valid year AND physically present in header_text
                if not (1900 <= pub_year <= 2100) or str(pub_year) not in header_text:
                    pub_year = None
            except (ValueError, TypeError):
                pub_year = None

        return HeaderMetadata(
            detected_publisher=parsed.get("detected_publisher") or None,
            detected_venue=parsed.get("detected_venue") or None,
            publication_year=pub_year,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Dynamic header metadata extraction failed (%s); proceeding with null metadata",
            type(exc).__name__,
        )
        return HeaderMetadata()


def get_document_metadata(doc_hash: str, db: Session) -> DocumentMetadata | None:
    """Retrieve DocumentMetadata record for a given document hash."""
    return (
        db.query(DocumentMetadata).filter(DocumentMetadata.doc_hash == doc_hash).first()
    )


def save_document_metadata(
    doc_hash: str,
    metadata: HeaderMetadata,
    title: str | None = None,
    authors: str | None = None,
    header_text: str | None = None,
    db: Session | None = None,
) -> DocumentMetadata | None:
    """Persist or update DocumentMetadata in the database."""
    if db is None:
        return None

    record = (
        db.query(DocumentMetadata).filter(DocumentMetadata.doc_hash == doc_hash).first()
    )
    if not record:
        record = DocumentMetadata(
            doc_hash=doc_hash,
            title=title,
            authors=authors,
            detected_publisher=metadata.detected_publisher,
            detected_venue=metadata.detected_venue,
            publication_year=metadata.publication_year,
            header_text=header_text,
        )
        db.add(record)
    else:
        if metadata.detected_publisher is not None:
            record.detected_publisher = metadata.detected_publisher
        if metadata.detected_venue is not None:
            record.detected_venue = metadata.detected_venue
        if metadata.publication_year is not None:
            record.publication_year = metadata.publication_year
        if title is not None:
            record.title = title
        if authors is not None:
            record.authors = authors
        if header_text is not None:
            record.header_text = header_text

    db.commit()
    db.refresh(record)
    return record
