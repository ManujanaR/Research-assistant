from io import BytesIO
from typing import Any
from pypdf import PdfReader


def parse_pdf(file_bytes: bytes) -> list[dict[str, Any]]:
    reader = PdfReader(BytesIO(file_bytes))
    pages: list[dict[str, Any]] = []
    for idx, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        pages.append({"page": idx + 1, "text": text.strip()})
    return pages
