"""Service for building editable Word (.docx) export documents."""

import io
from typing import Any

from docx import Document

from app.schemas.export import ExportMessage

DISCLAIMER_TEXT = (
    "Answers are grounded in retrieved passages of the uploaded paper. "
    "Verify against the source."
)

SUMMARY_SECTIONS = [
    ("Title, Authors & Abstract", "title_authors_abstract"),
    ("Problem Statement", "problem_statement"),
    ("Methodology", "methodology"),
    ("Key Results", "key_results"),
    ("Conclusion", "conclusion"),
]


def build_docx(
    summary: Any,
    filename: str,
    date: str,
    messages: list[ExportMessage] | list[dict[str, Any]] | None = None,
) -> bytes:
    """Build an in-memory Word document (.docx) from summary and conversation messages.

    Uses only python-docx. Writes text as plain runs and never interprets text as markup.
    Builds the file purely in memory without writing to disk.
    """
    doc = Document()

    # Footer on each page
    section = doc.sections[0]
    footer = section.footer
    footer_p = footer.paragraphs[0]
    footer_p.text = DISCLAIMER_TEXT

    # 1. Title
    doc.add_heading("Mitra Research Assistant Report", level=0)

    # 2. Filename
    p_fn = doc.add_paragraph()
    p_fn.add_run(filename)

    # 3. Generated date
    p_date = doc.add_paragraph()
    p_date.add_run(date)

    # 4. Five summary sections with headings in exact order
    for heading_title, field_name in SUMMARY_SECTIONS:
        doc.add_heading(heading_title, level=1)
        if isinstance(summary, dict):
            sec_text = summary.get(field_name, "")
        else:
            sec_text = getattr(summary, field_name, "")
        p_sec = doc.add_paragraph()
        p_sec.add_run(str(sec_text) if sec_text is not None else "")

    # 5. "My notes" heading after the summary, with an empty paragraph under it
    doc.add_heading("My notes", level=1)
    doc.add_paragraph("")

    # 6. Conversation section
    doc.add_heading("Conversation", level=1)

    if messages:
        for msg in messages:
            role = msg.role if hasattr(msg, "role") else msg.get("role")
            text = msg.text if hasattr(msg, "text") else msg.get("text", "")
            sources = msg.sources if hasattr(msg, "sources") else msg.get("sources", [])

            if role == "user":
                doc.add_heading("Question", level=2)
                p = doc.add_paragraph()
                p.add_run(str(text))
            elif role == "assistant":
                doc.add_heading("Answer", level=2)
                p = doc.add_paragraph()
                p.add_run(str(text))

                if sources:
                    doc.add_heading("Sources", level=3)
                    for idx, src in enumerate(sources, start=1):
                        page_num = (
                            src.page_number
                            if hasattr(src, "page_number")
                            else src.get("page_number")
                            if isinstance(src, dict)
                            else None
                        )
                        snippet = (
                            src.snippet
                            if hasattr(src, "snippet")
                            else src.get("snippet")
                            if isinstance(src, dict)
                            else None
                        )
                        parts = [f"[{idx}]"]
                        if page_num is not None:
                            parts.append(f"Page {page_num}")
                        if snippet:
                            parts.append(f"- {snippet}")
                        p_src = doc.add_paragraph()
                        p_src.add_run(" ".join(parts))

                doc.add_heading("My notes", level=2)
                doc.add_paragraph("")

    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()
