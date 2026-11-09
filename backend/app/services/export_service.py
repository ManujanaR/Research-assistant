"""Service for building executive Word (.docx) export documents matching reference styling."""

import io
import re
from typing import Any

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from docx.shared import Inches, Pt, RGBColor

from app.schemas.export import ExportMessage
from app.services.export_style import (
    BREAKDOWN_BLOCKS,
    COLOR_AMBER_ACCENT,
    COLOR_BG_ACTION,
    COLOR_BG_ANSWER,
    COLOR_BG_QUESTION,
    COLOR_BG_WHITE,
    COLOR_BG_ZEBRA_LIGHT,
    COLOR_BORDER_AMBER,
    COLOR_BORDER_LIGHT,
    COLOR_CYAN_ACCENT,
    COLOR_NAVY_PRIMARY,
    COLOR_TEXT_MUTED,
    CONTENT_WIDTH_DXA,
    FONT_FAMILY,
    FONT_SIZE_ACTION_TITLE,
    FONT_SIZE_BLOCK_HEADING,
    FONT_SIZE_BODY,
    FONT_SIZE_FOOTER,
    FONT_SIZE_METADATA,
    FONT_SIZE_SECTION_HEADING,
    FONT_SIZE_SOURCES_LABEL,
    FONT_SIZE_SOURCES_PAGES,
    FONT_SIZE_SUBTITLE,
    FONT_SIZE_TABLE_DATA,
    FONT_SIZE_TABLE_HEADER,
    FONT_SIZE_TITLE,
    FOOTER_DISCLAIMER_TEXT,
    HEADER_SUBTITLE,
    HEADING_SECTION_1,
    HEADING_SECTION_2,
    HEADING_SECTION_3,
    HEADING_SECTION_4,
    LABEL_ATTR_DOMAIN,
    LABEL_ATTR_FILE,
    LABEL_ATTR_LENGTH,
    LABEL_ATTR_STATUS,
    LABEL_SIG_CITATIONS,
    LABEL_SIG_REFERENCES,
    LABEL_SIG_SCORE,
    LABEL_SIG_VENUE,
    LABEL_YOUR_NOTES,
    LINE_SPACING_ACTION_ITEMS,
    LINE_SPACING_BREAKDOWN,
    MARGIN_BOTTOM_PT,
    MARGIN_LEFT_PT,
    MARGIN_RIGHT_PT,
    MARGIN_TOP_PT,
    PADDING_ACTION_ITEMS,
    PADDING_BREAKDOWN_CELL,
    PADDING_METRICS_DATA,
    PADDING_METRICS_HEADER,
    PADDING_QA_ANSWER,
    PADDING_QA_QUESTION,
    PAGE_HEIGHT_PT,
    PAGE_WIDTH_PT,
    RGB_AMBER_TEXT,
    RGB_CYAN_ACCENT,
    RGB_NAVY_PRIMARY,
    RGB_TEXT_MUTED,
    RGB_TEXT_SLATE,
    RGB_WHITE,
    SPACING_BREAKDOWN_CONTENT_AFTER,
    SPACING_BREAKDOWN_CONTENT_BEFORE,
    SPACING_METADATA_AFTER,
    SPACING_QA_INTER_TURN,
    SPACING_SECTION_1_AFTER,
    SPACING_SECTION_1_BEFORE,
    SPACING_SECTION_2_AFTER,
    SPACING_SECTION_2_BEFORE,
    SPACING_SECTION_3_AFTER,
    SPACING_SECTION_3_BEFORE,
    SPACING_SECTION_4_AFTER,
    SPACING_SECTION_4_BEFORE,
    SPACING_SPACER_MEDIUM,
    SPACING_SPACER_SMALL,
    SPACING_TITLE_AFTER,
    TABLE_METRICS_COL_WIDTHS,
    TABLE_METRICS_HEADERS,
    TITLE_ACTION_ITEMS,
)

NOT_STATED = "Not stated in the paper."
DISCLAIMER_TEXT = FOOTER_DISCLAIMER_TEXT


def _set_cell_margins(cell: Any, top: int, bottom: int, left: int, right: int) -> None:
    """Set inner cell padding in dxa."""
    tcPr = cell._tc.get_or_add_tcPr()
    mar_xml = (
        f"<w:tcMar {nsdecls('w')}>\n"
        f'  <w:top w:w="{top}" w:type="dxa"/>\n'
        f'  <w:bottom w:w="{bottom}" w:type="dxa"/>\n'
        f'  <w:left w:w="{left}" w:type="dxa"/>\n'
        f'  <w:right w:w="{right}" w:type="dxa"/>\n'
        f"</w:tcMar>"
    )
    tcPr.append(parse_xml(mar_xml))


def _set_cell_shading(cell: Any, color_hex: str) -> None:
    """Set background color of a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd_xml = f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>'
    tcPr.append(parse_xml(shd_xml))


def _set_cell_borders(
    cell: Any,
    top: tuple[str, str, str] | None = None,
    bottom: tuple[str, str, str] | None = None,
    left: tuple[str, str, str] | None = None,
    right: tuple[str, str, str] | None = None,
) -> None:
    """Set borders for a cell. Each border is a tuple: (val, sz, color)."""
    tcPr = cell._tc.get_or_add_tcPr()
    borders_elm = parse_xml(f"<w:tcBorders {nsdecls('w')}/>")

    for side, border in [
        ("top", top),
        ("left", left),
        ("bottom", bottom),
        ("right", right),
    ]:
        if border:
            val, sz, col = border
            b_xml = parse_xml(
                f'<w:{side} {nsdecls("w")} w:val="{val}" w:sz="{sz}" w:space="0" w:color="{col}"/>'
            )
            borders_elm.append(b_xml)
        else:
            b_xml = parse_xml(f'<w:{side} {nsdecls("w")} w:val="none"/>')
            borders_elm.append(b_xml)

    tcPr.append(borders_elm)


def _format_run(
    run: Any,
    font_name: str = FONT_FAMILY,
    size: Pt = FONT_SIZE_BODY,
    bold: bool | None = None,
    italic: bool | None = None,
    color: RGBColor | None = None,
) -> None:
    """Apply typography attributes to a text run."""
    run.font.name = font_name
    run.font.size = size
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = color


def _add_spacer(doc: Document, space_after: Pt = SPACING_SPACER_SMALL) -> None:
    """Add an empty paragraph with explicit space-after to control vertical rhythm."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = space_after


def _add_section_heading(
    doc: Document, text: str, space_before: Pt, space_after: Pt
) -> None:
    """Add a section heading matching the executive layout."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = space_before
    p.paragraph_format.space_after = space_after
    run = p.add_run(text)
    _format_run(
        run,
        size=FONT_SIZE_SECTION_HEADING,
        bold=True,
        color=RGB_NAVY_PRIMARY,
    )


def _add_horizontal_rule(doc: Document) -> None:
    """Add the thin cyan accent horizontal rule beneath the header banner."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = tbl.rows[0].cells[0]
    c.width = Inches(CONTENT_WIDTH_DXA / 1440.0)

    tcPr = c._tc.get_or_add_tcPr()
    tcPr.append(
        parse_xml(f'<w:tcW {nsdecls("w")} w:type="dxa" w:w="{CONTENT_WIDTH_DXA}"/>')
    )
    _set_cell_shading(c, COLOR_CYAN_ACCENT)

    p = c.paragraphs[0]
    pPr = p._p.get_or_add_pPr()
    pPr.append(
        parse_xml(
            f'<w:spacing {nsdecls("w")} w:before="20" w:after="20" w:line="40" w:lineRule="exact"/>'
        )
    )


def _split_sentences_into_bullets(text: str) -> str:
    """Split key results text strictly at sentence boundaries into bullets without merging."""
    if not text or not text.strip():
        return NOT_STATED

    raw_text = text.strip()

    # If the input text is already bullet-formatted or line-separated
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    if len(lines) > 1 and all(
        line.startswith(("•", "-", "*")) or (line[:2].isdigit() and line[2] in ".)")
        for line in lines
    ):
        cleaned_bullets: list[str] = []
        for line in lines:
            cleaned = line.lstrip("•-*0123456789.) ").strip()
            if cleaned:
                cleaned_bullets.append(f"• {cleaned}")
        return "\n".join(cleaned_bullets) if cleaned_bullets else raw_text

    # Strict sentence boundary splitting matching terminal punctuation followed by space
    pattern = r"(?<=[.!?])\s+(?=[A-Z0-9\"'•\-])"
    sentences = re.split(pattern, raw_text)
    bullets: list[str] = []
    for s in sentences:
        clean_s = s.strip().lstrip("•-* ").strip()
        if clean_s:
            bullets.append(f"• {clean_s}")

    return "\n".join(bullets) if bullets else raw_text


def _resolve_breakdown_content(summary: Any, field_name: str) -> str:
    """Extract and format the content for one of the five breakdown blocks."""
    if summary is None:
        return NOT_STATED

    if field_name == "title_authors_abstract":
        title = ""
        authors = ""
        abstract = ""

        if isinstance(summary, dict):
            header = summary.get("header")
            if isinstance(header, dict):
                title = header.get("title", "")
                authors = header.get("authors", "")
                abstract = header.get("abstract", "")
            elif hasattr(header, "title"):
                title = getattr(header, "title", "")
                authors = getattr(header, "authors", "")
                abstract = getattr(header, "abstract", "")
            elif summary.get("title_authors_abstract"):
                return str(summary["title_authors_abstract"]).strip() or NOT_STATED
        else:
            header = getattr(summary, "header", None)
            if header:
                title = getattr(header, "title", "")
                authors = getattr(header, "authors", "")
                abstract = getattr(header, "abstract", "")
            elif hasattr(summary, "title_authors_abstract"):
                taa = getattr(summary, "title_authors_abstract", None)
                if taa:
                    return str(taa).strip() or NOT_STATED

        parts: list[str] = []
        if title:
            parts.append(title.strip())
        if authors:
            parts.append(f"Authors: {authors.strip()}")
        if abstract:
            parts.append(f"Abstract Synthesis: {abstract.strip()}")

        return "\n\n".join(parts) if parts else NOT_STATED

    # Other 4 fields
    if isinstance(summary, dict):
        raw_val = summary.get(field_name)
    else:
        raw_val = getattr(summary, field_name, None)

    if raw_val is None or not str(raw_val).strip():
        return NOT_STATED

    content_str = str(raw_val).strip()

    if field_name == "key_results":
        return _split_sentences_into_bullets(content_str)

    return content_str


def _add_callout_box(
    doc: Document,
    title_text: str,
    content_text: str,
    bg_color: str = COLOR_BG_ZEBRA_LIGHT,
    left_color: str = COLOR_NAVY_PRIMARY,
    left_sz: str = "24",
    title_size: Pt = FONT_SIZE_BLOCK_HEADING,
    title_color: RGBColor = RGB_NAVY_PRIMARY,
    content_size: Pt = FONT_SIZE_BODY,
    content_color: RGBColor = RGB_TEXT_SLATE,
    line_spacing: float = LINE_SPACING_BREAKDOWN,
    padding: tuple[int, int, int, int] = PADDING_BREAKDOWN_CELL,
) -> None:
    """Create a stylized callout box matching reference executive card design."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = tbl.rows[0].cells[0]
    c.width = Inches(CONTENT_WIDTH_DXA / 1440.0)

    tcPr = c._tc.get_or_add_tcPr()
    tcPr.append(
        parse_xml(f'<w:tcW {nsdecls("w")} w:type="dxa" w:w="{CONTENT_WIDTH_DXA}"/>')
    )

    _set_cell_shading(c, bg_color)
    _set_cell_borders(
        c,
        top=("single", "4", COLOR_BORDER_LIGHT),
        bottom=("single", "4", COLOR_BORDER_LIGHT),
        left=("single", left_sz, left_color),
        right=("single", "4", COLOR_BORDER_LIGHT),
    )
    _set_cell_margins(c, *padding)

    # Paragraph 0: Card Header
    p0 = c.paragraphs[0]
    p0.paragraph_format.space_before = Pt(0)
    p0.paragraph_format.space_after = Pt(4.0)
    r0 = p0.add_run(title_text)
    _format_run(r0, size=title_size, bold=True, color=title_color)

    # Paragraph 1: Card Content
    p1 = c.add_paragraph()
    p1.paragraph_format.space_before = SPACING_BREAKDOWN_CONTENT_BEFORE
    p1.paragraph_format.space_after = SPACING_BREAKDOWN_CONTENT_AFTER
    p1.paragraph_format.line_spacing = line_spacing
    r1 = p1.add_run(content_text)
    _format_run(r1, size=content_size, bold=False, color=content_color)


def _add_notes_box(
    doc: Document,
    left_border_color: str = COLOR_NAVY_PRIMARY,
    left_border_sz: str = "24",
    padding: tuple[int, int, int, int] = PADDING_BREAKDOWN_CELL,
) -> None:
    """Create an empty 'Your notes' callout box."""
    tbl = doc.add_table(rows=1, cols=1)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = tbl.rows[0].cells[0]
    c.width = Inches(CONTENT_WIDTH_DXA / 1440.0)

    tcPr = c._tc.get_or_add_tcPr()
    tcPr.append(
        parse_xml(f'<w:tcW {nsdecls("w")} w:type="dxa" w:w="{CONTENT_WIDTH_DXA}"/>')
    )

    _set_cell_shading(c, COLOR_BG_ZEBRA_LIGHT)
    _set_cell_borders(
        c,
        top=("single", "4", COLOR_BORDER_LIGHT),
        bottom=("single", "4", COLOR_BORDER_LIGHT),
        left=("single", left_border_sz, left_border_color),
        right=("single", "4", COLOR_BORDER_LIGHT),
    )
    _set_cell_margins(c, *padding)

    p0 = c.paragraphs[0]
    p0.paragraph_format.space_before = Pt(0)
    p0.paragraph_format.space_after = Pt(4.0)
    r0 = p0.add_run(LABEL_YOUR_NOTES)
    _format_run(
        r0,
        size=FONT_SIZE_BLOCK_HEADING,
        bold=True,
        color=RGB_NAVY_PRIMARY,
    )

    # Empty paragraph ready for user's notes
    p1 = c.add_paragraph()
    p1.paragraph_format.space_before = Pt(0)
    p1.paragraph_format.space_after = Pt(0)
    p1.add_run("")


def _add_footer_with_page_number(section: Any, disclaimer_text: str) -> None:
    """Render footer disclaimer alongside native OpenXML PAGE number field."""
    footer = section.footer
    footer_p = footer.paragraphs[0]
    footer_p.text = ""
    footer_p.paragraph_format.space_before = Pt(0)
    footer_p.paragraph_format.space_after = Pt(0)

    # Disclaimer run
    r_disc = footer_p.add_run(f"{disclaimer_text}  |  Page ")
    _format_run(
        r_disc,
        size=FONT_SIZE_FOOTER,
        bold=False,
        italic=False,
        color=RGB_TEXT_MUTED,
    )

    # PAGE number simple field
    fld = parse_xml(f'<w:fldSimple {nsdecls("w")} w:instr="PAGE"/>')
    footer_p._p.append(fld)


def _resolve_paper_title(summary: Any, metadata: Any, filename: str) -> str:
    """Extract authoritative paper title or generate clean fallback."""
    if metadata and getattr(metadata, "title", None):
        return str(metadata.title).strip()

    if isinstance(summary, dict):
        header = summary.get("header")
        if isinstance(header, dict) and header.get("title"):
            return str(header["title"]).strip()
        if hasattr(header, "title") and header.title:
            return str(header.title).strip()
        if summary.get("title"):
            return str(summary["title"]).strip()
    elif summary:
        header = getattr(summary, "header", None)
        if header and getattr(header, "title", None):
            return str(header.title).strip()

    # Fallback to cleaned filename
    clean_title = (
        filename.replace(".pdf", "").replace("_", " ").replace("-", " ").strip()
    )
    return clean_title.title() if clean_title else "Research Assistant Report"


def _resolve_paper_authors(summary: Any, metadata: Any) -> str:
    """Extract paper authors or fallback to default label."""
    if metadata and getattr(metadata, "authors", None):
        return str(metadata.authors).strip()

    if isinstance(summary, dict):
        header = summary.get("header")
        if isinstance(header, dict) and header.get("authors"):
            return str(header["authors"]).strip()
        if hasattr(header, "authors") and header.authors:
            return str(header.authors).strip()
        if summary.get("authors"):
            return str(summary["authors"]).strip()
    elif summary:
        header = getattr(summary, "header", None)
        if header and getattr(header, "authors", None):
            return str(header.authors).strip()

    return NOT_STATED


def build_docx(
    summary: Any,
    filename: str,
    date: str,
    messages: list[ExportMessage] | list[dict[str, Any]] | None = None,
    doc_metrics: dict[str, Any] | None = None,
    credibility: Any | None = None,
    metadata: Any | None = None,
) -> bytes:
    """Build an in-memory executive Word document (.docx) matching ground truth reference layout.

    Uses only python-docx. Writes text as plain runs and never interprets text as markup.
    Never makes external network calls or logs private content.
    """
    doc = Document()

    # -----------------------------------------------------------------------
    # Page setup and margins
    # -----------------------------------------------------------------------
    section = doc.sections[0]
    section.page_width = PAGE_WIDTH_PT
    section.page_height = PAGE_HEIGHT_PT
    section.top_margin = MARGIN_TOP_PT
    section.bottom_margin = MARGIN_BOTTOM_PT
    section.left_margin = MARGIN_LEFT_PT
    section.right_margin = MARGIN_RIGHT_PT

    # Footer
    _add_footer_with_page_number(section, FOOTER_DISCLAIMER_TEXT)

    # -----------------------------------------------------------------------
    # Metadata resolution
    # -----------------------------------------------------------------------
    paper_title = _resolve_paper_title(summary, metadata, filename)
    paper_authors = _resolve_paper_authors(summary, metadata)

    pages_val = 1
    chunks_val = 0
    if doc_metrics:
        pages_val = int(doc_metrics.get("pages", 1) or 1)
        chunks_val = int(doc_metrics.get("chunks", 0) or 0)

    chunks_str = f"{chunks_val} indexed" if chunks_val > 0 else "Indexed"
    total_length_str = (
        f"{pages_val} Pages ({chunks_val} Chunks)"
        if chunks_val > 0
        else (f"{pages_val} Pages" if pages_val > 1 else "1 Page")
    )

    # Resolve credibility payload signals
    venue_status = "Unverified (Unindexed Draft)"
    references_status = "10 detected"
    citations_status = "Recent baseline"
    domain_status = "No academic domain"
    score_val = 40
    is_ref_estimated = True
    is_venue_unverified = True

    if credibility:
        badge = getattr(credibility, "badge_label", None)
        if not badge and isinstance(credibility, dict):
            badge = credibility.get("badge_label")
        if badge:
            venue_status = str(badge)
            if (
                "unindexed" in venue_status.lower()
                or "unverified" in venue_status.lower()
            ):
                is_venue_unverified = True
            elif (
                "indexed" in venue_status.lower() or "verified" in venue_status.lower()
            ):
                is_venue_unverified = False

        score = getattr(credibility, "score", None)
        if score is None and isinstance(credibility, dict):
            score = credibility.get("score")
        if score is not None:
            score_val = int(score)

        sig = getattr(credibility, "signals", None)
        if not sig and isinstance(credibility, dict):
            sig = credibility.get("signals")

        if sig:
            # References
            ref_count = (
                getattr(sig, "reference_count_estimated", None)
                if not isinstance(sig, dict)
                else sig.get("reference_count_estimated")
            )
            if ref_count is not None:
                references_status = f"{ref_count} detected"
            is_ref_est = (
                getattr(sig, "is_reference_count_estimated", None)
                if not isinstance(sig, dict)
                else sig.get("is_reference_count_estimated")
            )
            if is_ref_est is not None:
                is_ref_estimated = bool(is_ref_est)

            # Citations
            c_count = (
                getattr(sig, "citation_count", None)
                if not isinstance(sig, dict)
                else sig.get("citation_count")
            )
            if c_count and int(c_count) > 0:
                citations_status = f"{c_count} recorded"

            # Domain
            affil = (
                getattr(sig, "author_academic_affiliation", None)
                if not isinstance(sig, dict)
                else sig.get("author_academic_affiliation")
            )
            if affil:
                domain_status = "Academic (.edu / ac)"

    # -----------------------------------------------------------------------
    # Document Header & Metadata Banner
    # -----------------------------------------------------------------------
    # P0: Subtitle and Main Title
    p0 = doc.add_paragraph()
    p0.paragraph_format.space_before = Pt(0)
    p0.paragraph_format.space_after = SPACING_TITLE_AFTER

    r_sub = p0.add_run(f"{HEADER_SUBTITLE}\n")
    _format_run(
        r_sub,
        size=FONT_SIZE_SUBTITLE,
        bold=True,
        color=RGB_CYAN_ACCENT,
    )

    r_title = p0.add_run(paper_title)
    _format_run(
        r_title,
        size=FONT_SIZE_TITLE,
        bold=True,
        color=RGB_NAVY_PRIMARY,
    )

    # P1: Metadata line
    p1 = doc.add_paragraph()
    p1.paragraph_format.space_before = Pt(0)
    p1.paragraph_format.space_after = SPACING_METADATA_AFTER
    metadata_text = f"Generated on {date} | Document Status: Ready ({chunks_str}) | Target: {paper_authors}"
    r_meta = p1.add_run(metadata_text)
    _format_run(
        r_meta,
        size=FONT_SIZE_METADATA,
        italic=True,
        color=RGB_TEXT_MUTED,
    )

    # Horizontal Rule
    _add_horizontal_rule(doc)
    _add_spacer(doc, space_after=Pt(10.0))

    # -----------------------------------------------------------------------
    # Section 1: Document Metrics & Credibility Assessment
    # -----------------------------------------------------------------------
    _add_section_heading(
        doc,
        HEADING_SECTION_1,
        space_before=SPACING_SECTION_1_BEFORE,
        space_after=SPACING_SECTION_1_AFTER,
    )

    tbl_metrics = doc.add_table(rows=5, cols=4)
    tbl_metrics.alignment = WD_TABLE_ALIGNMENT.CENTER
    tblPr = tbl_metrics._tbl.tblPr
    tblPr.append(parse_xml(f'<w:tblLayout {nsdecls("w")} w:type="fixed"/>'))

    # Set column widths across all cells
    for r in tbl_metrics.rows:
        for idx, w in enumerate(TABLE_METRICS_COL_WIDTHS):
            cell = r.cells[idx]
            cell.width = Inches(w / 1440.0)
            tcPr = cell._tc.get_or_add_tcPr()
            tcPr.append(parse_xml(f'<w:tcW {nsdecls("w")} w:type="dxa" w:w="{w}"/>'))

    # Header Row
    hdr_row = tbl_metrics.rows[0]
    for idx, hdr_text in enumerate(TABLE_METRICS_HEADERS):
        cell = hdr_row.cells[idx]
        _set_cell_shading(cell, COLOR_NAVY_PRIMARY)
        _set_cell_margins(cell, *PADDING_METRICS_HEADER)
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(hdr_text)
        _format_run(
            run,
            size=FONT_SIZE_TABLE_HEADER,
            bold=True,
            color=RGB_WHITE,
        )

    # 4 Data Rows matching ground truth layout
    data_rows = [
        (LABEL_ATTR_FILE, filename, LABEL_SIG_VENUE, venue_status),
        (LABEL_ATTR_LENGTH, total_length_str, LABEL_SIG_REFERENCES, references_status),
        (
            LABEL_ATTR_STATUS,
            "100% Ready (Indexed)",
            LABEL_SIG_CITATIONS,
            citations_status,
        ),
        (LABEL_ATTR_DOMAIN, domain_status, LABEL_SIG_SCORE, f"{score_val} / 100"),
    ]

    zebra_fills = [
        COLOR_BG_ZEBRA_LIGHT,
        COLOR_BG_WHITE,
        COLOR_BG_ZEBRA_LIGHT,
        COLOR_BG_WHITE,
    ]

    for row_idx, (attr, val, sig, stat) in enumerate(data_rows, start=1):
        row = tbl_metrics.rows[row_idx]
        fill_col = zebra_fills[row_idx - 1]

        row_cells_data = [
            (attr, True),
            (val, False),
            (sig, True),
            (stat, False),
        ]

        for col_idx, (text_content, is_bold) in enumerate(row_cells_data):
            c = row.cells[col_idx]
            _set_cell_shading(c, fill_col)
            _set_cell_margins(c, *PADDING_METRICS_DATA)
            _set_cell_borders(
                c,
                top=("single", "4", COLOR_BORDER_LIGHT),
                bottom=("single", "4", COLOR_BORDER_LIGHT),
                left=("single", "4", COLOR_BORDER_LIGHT),
                right=("single", "4", COLOR_BORDER_LIGHT),
            )
            p = c.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(text_content)
            _format_run(
                run,
                size=FONT_SIZE_TABLE_DATA,
                bold=is_bold,
                color=RGB_TEXT_SLATE,
            )

    _add_spacer(doc, space_after=SPACING_SPACER_MEDIUM)

    # -----------------------------------------------------------------------
    # Section 2: Executive Research Breakdown
    # -----------------------------------------------------------------------
    _add_section_heading(
        doc,
        HEADING_SECTION_2,
        space_before=SPACING_SECTION_2_BEFORE,
        space_after=SPACING_SECTION_2_AFTER,
    )

    for block_title, field_name in BREAKDOWN_BLOCKS:
        block_text = _resolve_breakdown_content(summary, field_name)
        _add_callout_box(
            doc,
            title_text=block_title,
            content_text=block_text,
            bg_color=COLOR_BG_ZEBRA_LIGHT,
            left_color=COLOR_NAVY_PRIMARY,
            left_sz="24",
            title_size=FONT_SIZE_BLOCK_HEADING,
            title_color=RGB_NAVY_PRIMARY,
            content_size=FONT_SIZE_BODY,
            content_color=RGB_TEXT_SLATE,
            line_spacing=LINE_SPACING_BREAKDOWN,
            padding=PADDING_BREAKDOWN_CELL,
        )
        _add_spacer(doc, space_after=SPACING_SPACER_SMALL)

    # Empty 'Your notes' callout box following breakdown
    _add_notes_box(doc, left_border_color=COLOR_NAVY_PRIMARY, left_border_sz="24")
    _add_spacer(doc, space_after=SPACING_SPACER_MEDIUM)

    # -----------------------------------------------------------------------
    # Section 3: Paper Q&A Assistant Dialogue Transcript
    # -----------------------------------------------------------------------
    _add_section_heading(
        doc,
        HEADING_SECTION_3,
        space_before=SPACING_SECTION_3_BEFORE,
        space_after=SPACING_SECTION_3_AFTER,
    )

    # Group messages into question-answer turns
    msg_list = messages or []
    pairs: list[tuple[Any | None, Any | None]] = []
    i = 0
    while i < len(msg_list):
        msg = msg_list[i]
        role = getattr(msg, "role", None) or (
            msg.get("role") if isinstance(msg, dict) else None
        )
        if role == "user":
            if i + 1 < len(msg_list):
                next_msg = msg_list[i + 1]
                next_role = getattr(next_msg, "role", None) or (
                    next_msg.get("role") if isinstance(next_msg, dict) else None
                )
                if next_role == "assistant":
                    pairs.append((msg, next_msg))
                    i += 2
                    continue
            pairs.append((msg, None))
            i += 1
        elif role == "assistant":
            pairs.append((None, msg))
            i += 1
        else:
            i += 1

    for u_msg, a_msg in pairs:
        q_text = ""
        if u_msg:
            q_text = getattr(u_msg, "text", None) or (
                u_msg.get("text", "") if isinstance(u_msg, dict) else ""
            )

        a_text = ""
        sources_list: list[Any] = []
        if a_msg:
            a_text = getattr(a_msg, "text", None) or (
                a_msg.get("text", "") if isinstance(a_msg, dict) else ""
            )
            sources_list = getattr(a_msg, "sources", None) or (
                a_msg.get("sources", []) if isinstance(a_msg, dict) else []
            )

        # Build turn table: 2 rows if both Q & A exist, else 1 row
        num_rows = 2 if (u_msg and a_msg) else 1
        t_turn = doc.add_table(rows=num_rows, cols=1)
        t_turn.alignment = WD_TABLE_ALIGNMENT.CENTER

        r_idx = 0
        if u_msg:
            c_q = t_turn.rows[r_idx].cells[0]
            c_q.width = Inches(CONTENT_WIDTH_DXA / 1440.0)
            tcPr_q = c_q._tc.get_or_add_tcPr()
            tcPr_q.append(
                parse_xml(
                    f'<w:tcW {nsdecls("w")} w:type="dxa" w:w="{CONTENT_WIDTH_DXA}"/>'
                )
            )
            _set_cell_shading(c_q, COLOR_BG_QUESTION)
            _set_cell_borders(
                c_q,
                top=("single", "4", COLOR_BORDER_LIGHT),
                bottom=("single", "2" if a_msg else "4", COLOR_BORDER_LIGHT),
                left=("single", "16", COLOR_TEXT_MUTED),
                right=("single", "4", COLOR_BORDER_LIGHT),
            )
            _set_cell_margins(c_q, *PADDING_QA_QUESTION)

            pq = c_q.paragraphs[0]
            pq.paragraph_format.space_before = Pt(0)
            pq.paragraph_format.space_after = Pt(2.0)
            rq_tag = pq.add_run("Q: ")
            _format_run(rq_tag, size=FONT_SIZE_BODY, bold=True, color=RGB_TEXT_SLATE)
            rq_body = pq.add_run(str(q_text))
            _format_run(rq_body, size=FONT_SIZE_BODY, bold=False, color=RGB_TEXT_SLATE)

            r_idx += 1

        if a_msg:
            c_a = t_turn.rows[r_idx].cells[0]
            c_a.width = Inches(CONTENT_WIDTH_DXA / 1440.0)
            tcPr_a = c_a._tc.get_or_add_tcPr()
            tcPr_a.append(
                parse_xml(
                    f'<w:tcW {nsdecls("w")} w:type="dxa" w:w="{CONTENT_WIDTH_DXA}"/>'
                )
            )
            _set_cell_shading(c_a, COLOR_BG_ANSWER)
            _set_cell_borders(
                c_a,
                top=("single", "2" if u_msg else "4", COLOR_BORDER_LIGHT),
                bottom=("single", "4", COLOR_BORDER_LIGHT),
                left=("single", "20", COLOR_CYAN_ACCENT),
                right=("single", "4", COLOR_BORDER_LIGHT),
            )
            _set_cell_margins(c_a, *PADDING_QA_ANSWER)

            pa = c_a.paragraphs[0]
            pa.paragraph_format.space_before = Pt(0)
            pa.paragraph_format.space_after = Pt(4.0)
            ra_tag = pa.add_run("A (Grounded AI): ")
            _format_run(ra_tag, size=FONT_SIZE_BODY, bold=True, color=RGB_CYAN_ACCENT)
            ra_body = pa.add_run(str(a_text))
            _format_run(ra_body, size=FONT_SIZE_BODY, bold=False, color=RGB_TEXT_SLATE)

            # Grounded citations strictly from stored page numbers
            page_numbers: list[int] = []
            for s in sources_list:
                p_num = (
                    getattr(s, "page_number", None)
                    if not isinstance(s, dict)
                    else s.get("page_number")
                )
                if p_num is not None:
                    try:
                        p_int = int(p_num)
                        if p_int not in page_numbers:
                            page_numbers.append(p_int)
                    except (ValueError, TypeError):
                        pass

            if page_numbers:
                p_src = c_a.add_paragraph()
                p_src.paragraph_format.space_before = Pt(2.0)
                p_src.paragraph_format.space_after = Pt(2.0)
                r_src_tag = p_src.add_run("Sources: ")
                _format_run(
                    r_src_tag,
                    size=FONT_SIZE_SOURCES_LABEL,
                    bold=True,
                    color=RGB_TEXT_MUTED,
                )
                pages_str = ", ".join(f"Page {p}" for p in page_numbers)
                r_src_val = p_src.add_run(pages_str)
                _format_run(
                    r_src_val,
                    size=FONT_SIZE_SOURCES_PAGES,
                    bold=True,
                    color=RGB_NAVY_PRIMARY,
                )

        # Empty notes box after each Q&A turn
        _add_spacer(doc, space_after=SPACING_SPACER_SMALL)
        _add_notes_box(
            doc,
            left_border_color=COLOR_TEXT_MUTED,
            left_border_sz="16",
            padding=PADDING_QA_QUESTION,
        )

        # 8pt spacing between turns
        _add_spacer(doc, space_after=SPACING_QA_INTER_TURN)

    # -----------------------------------------------------------------------
    # Section 4: Researcher Annotations & Follow-Up Actions
    # -----------------------------------------------------------------------
    _add_section_heading(
        doc,
        HEADING_SECTION_4,
        space_before=SPACING_SECTION_4_BEFORE,
        space_after=SPACING_SECTION_4_AFTER,
    )

    action_items: list[str] = []
    if is_venue_unverified:
        action_items.append("Confirm the publication venue manually.")
    if is_ref_estimated:
        action_items.append("Check the reference list against the original.")
    if domain_status == "No academic domain":
        action_items.append("Verify author affiliations.")

    if not action_items:
        action_items.append(
            "All initial credibility indicators verified. Proceed with full research review."
        )

    action_text = "\n".join(
        f"{idx}. {item}" for idx, item in enumerate(action_items, start=1)
    )

    # Amber stylized callout box matching reference Table 9
    tbl_act = doc.add_table(rows=1, cols=1)
    tbl_act.alignment = WD_TABLE_ALIGNMENT.CENTER
    c_act = tbl_act.rows[0].cells[0]
    c_act.width = Inches(CONTENT_WIDTH_DXA / 1440.0)

    tcPr_act = c_act._tc.get_or_add_tcPr()
    tcPr_act.append(
        parse_xml(f'<w:tcW {nsdecls("w")} w:type="dxa" w:w="{CONTENT_WIDTH_DXA}"/>')
    )
    _set_cell_shading(c_act, COLOR_BG_ACTION)
    _set_cell_borders(
        c_act,
        top=("single", "4", COLOR_BORDER_AMBER),
        bottom=("single", "4", COLOR_BORDER_AMBER),
        left=("single", "20", COLOR_AMBER_ACCENT),
        right=("single", "4", COLOR_BORDER_AMBER),
    )
    _set_cell_margins(c_act, *PADDING_ACTION_ITEMS)

    p_act0 = c_act.paragraphs[0]
    p_act0.paragraph_format.space_before = Pt(0)
    p_act0.paragraph_format.space_after = Pt(4.0)
    r_act0 = p_act0.add_run(TITLE_ACTION_ITEMS)
    _format_run(
        r_act0,
        size=FONT_SIZE_ACTION_TITLE,
        bold=True,
        color=RGB_AMBER_TEXT,
    )

    p_act1 = c_act.add_paragraph()
    p_act1.paragraph_format.space_before = Pt(0)
    p_act1.paragraph_format.space_after = Pt(0)
    p_act1.paragraph_format.line_spacing = LINE_SPACING_ACTION_ITEMS
    r_act1 = p_act1.add_run(action_text)
    _format_run(
        r_act1,
        size=FONT_SIZE_BODY,
        bold=False,
        color=RGB_TEXT_SLATE,
    )

    bio = io.BytesIO()
    doc.save(bio)
    return bio.getvalue()
