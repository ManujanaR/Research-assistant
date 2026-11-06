import re
from typing import Any

SECTION_PATTERN = re.compile(
    r"^(?:\d+[\.\d]*\s+)?(abstract|introduction|background|related work|methodology|methods|approach|system design|architecture|experiments|results|evaluation|discussion|conclusion|conclusions|references)\b",
    re.IGNORECASE,
)


def _is_section_header(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 80:
        return False
    if SECTION_PATTERN.match(s):
        return True
    if re.match(r"^\d+(\.\d+)*\s+[A-Z]", s):
        return True
    if re.match(r"^[A-Z][A-Z\s]{2,40}$", s) and 1 <= len(s.split()) <= 4:
        return True
    return False


def chunk_pages(
    pages: list[dict[str, Any]], chunk_size: int = 1000
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    current_section = "Abstract"

    for page_item in pages:
        page_num: int = int(page_item["page"])
        text: str = str(page_item["text"])
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        current_lines: list[str] = []
        current_len = 0

        for line in lines:
            if _is_section_header(line):
                if current_lines:
                    chunks.append(
                        {
                            "page": page_num,
                            "section": current_section,
                            "text": " ".join(current_lines),
                        }
                    )
                    current_lines = []
                    current_len = 0
                current_section = line

            if len(line) > chunk_size:
                if current_lines:
                    chunks.append(
                        {
                            "page": page_num,
                            "section": current_section,
                            "text": " ".join(current_lines),
                        }
                    )
                    current_lines = []
                    current_len = 0
                for i in range(0, len(line), chunk_size):
                    chunks.append(
                        {
                            "page": page_num,
                            "section": current_section,
                            "text": line[i : i + chunk_size],
                        }
                    )
                continue

            current_lines.append(line)
            current_len += len(line) + 1
            if current_len >= chunk_size:
                chunks.append(
                    {
                        "page": page_num,
                        "section": current_section,
                        "text": " ".join(current_lines),
                    }
                )
                current_lines = []
                current_len = 0

        if current_lines:
            chunks.append(
                {
                    "page": page_num,
                    "section": current_section,
                    "text": " ".join(current_lines),
                }
            )

    return chunks
