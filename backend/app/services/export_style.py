"""Central styling constants extracted from the executive reference DOCX.

Ground truth extracted from Research_Assistant_Dashboard_Export.docx:
- Subtitle: RESEARCH ASSISTANT • AI SYNTHESIS REPORT (Calibri 9.5pt, bold, 0284C7)
- Paper Title: Calibri 22pt, bold, 1E3A8A
- Metadata banner: Calibri 9.5pt, italic, 64748B
- Section Headings: Calibri 13pt, bold, 1E3A8A
- Colors: Header navy (#1E3A8A), Text slate (#1E293B), Accent sky (#0284C7),
  Muted slate (#64748B), Border slate (#CBD5E1), Amber accent (#D97706)
- Table 1 widths: 2592, 2304, 2592, 2304 dxa (Total 9792 dxa = 6.8 in)
- Exact headings and labels matching the reference file.
"""

from docx.shared import Pt, RGBColor

# ---------------------------------------------------------------------------
# Document Page Setup & Geometry
# ---------------------------------------------------------------------------
PAGE_WIDTH_PT = Pt(612.0)  # 8.5 inches
PAGE_HEIGHT_PT = Pt(792.0)  # 11.0 inches
MARGIN_TOP_PT = Pt(57.6)  # 0.8 inches (1152 dxa)
MARGIN_BOTTOM_PT = Pt(57.6)  # 0.8 inches (1152 dxa)
MARGIN_LEFT_PT = Pt(61.2)  # 0.85 inches (1224 dxa)
MARGIN_RIGHT_PT = Pt(61.2)  # 0.85 inches (1224 dxa)
CONTENT_WIDTH_DXA = 9792  # 6.8 inches printable width

# ---------------------------------------------------------------------------
# Color Palette (Hex values without '#')
# ---------------------------------------------------------------------------
COLOR_NAVY_PRIMARY = (
    "1E3A8A"  # Deep Navy: Title, headings, table header, breakdown accent
)
COLOR_CYAN_ACCENT = (
    "0284C7"  # Sky/Cyan: Subtitle, HR bar, AI answer left border & label
)
COLOR_TEXT_SLATE = "1E293B"  # Body slate text
COLOR_TEXT_MUTED = "64748B"  # Metadata, question border, source label, footer
COLOR_BORDER_LIGHT = "CBD5E1"  # Table and card outline border
COLOR_BORDER_AMBER = "E2E8F0"  # Action items top/bottom/right border
COLOR_AMBER_ACCENT = "D97706"  # Amber-600: Action items left accent border
COLOR_AMBER_TEXT = "B45309"  # Amber-700: Action items header title
COLOR_BG_WHITE = "FFFFFF"  # White table zebra row
COLOR_BG_ZEBRA_LIGHT = "F8FAFC"  # Light zebra row, breakdown box bg, notes box bg
COLOR_BG_QUESTION = "F1F5F9"  # Question callout bg
COLOR_BG_ANSWER = "EFF6FF"  # Answer callout bg
COLOR_BG_ACTION = "FCFBF7"  # Action items callout bg

# RGBColor equivalents for docx run font styling
RGB_NAVY_PRIMARY = RGBColor(0x1E, 0x3A, 0x8A)
RGB_CYAN_ACCENT = RGBColor(0x02, 0x84, 0xC7)
RGB_TEXT_SLATE = RGBColor(0x1E, 0x29, 0x3B)
RGB_TEXT_MUTED = RGBColor(0x64, 0x74, 0x8B)
RGB_AMBER_TEXT = RGBColor(0xB4, 0x53, 0x09)
RGB_WHITE = RGBColor(0xFF, 0xFF, 0xFF)

# ---------------------------------------------------------------------------
# Typography & Font Sizes
# ---------------------------------------------------------------------------
FONT_FAMILY = "Calibri"

FONT_SIZE_SUBTITLE = Pt(9.5)
FONT_SIZE_TITLE = Pt(22.0)
FONT_SIZE_METADATA = Pt(9.5)
FONT_SIZE_SECTION_HEADING = Pt(13.0)
FONT_SIZE_BLOCK_HEADING = Pt(10.5)
FONT_SIZE_BODY = Pt(9.5)
FONT_SIZE_TABLE_HEADER = Pt(9.5)
FONT_SIZE_TABLE_DATA = Pt(9.0)
FONT_SIZE_ACTION_TITLE = Pt(10.0)
FONT_SIZE_SOURCES_LABEL = Pt(8.5)
FONT_SIZE_SOURCES_PAGES = Pt(8.0)
FONT_SIZE_FOOTER = Pt(8.5)

# ---------------------------------------------------------------------------
# Spacing & Paragraph Formats
# ---------------------------------------------------------------------------
SPACING_TITLE_AFTER = Pt(2.0)  # 40 dxa
SPACING_METADATA_AFTER = Pt(14.0)  # 280 dxa

SPACING_SECTION_1_BEFORE = Pt(10.0)  # 200 dxa
SPACING_SECTION_1_AFTER = Pt(4.0)  # 80 dxa

SPACING_SECTION_2_BEFORE = Pt(12.0)  # 240 dxa
SPACING_SECTION_2_AFTER = Pt(6.0)  # 120 dxa

SPACING_SECTION_3_BEFORE = Pt(14.0)  # 280 dxa
SPACING_SECTION_3_AFTER = Pt(6.0)  # 120 dxa

SPACING_SECTION_4_BEFORE = Pt(12.0)  # 240 dxa
SPACING_SECTION_4_AFTER = Pt(4.0)  # 80 dxa

SPACING_SPACER_SMALL = Pt(4.0)  # 80 dxa
SPACING_SPACER_MEDIUM = Pt(8.0)  # 160 dxa
SPACING_SPACER_LARGE = Pt(10.0)  # 200 dxa
SPACING_QA_INTER_TURN = Pt(8.0)  # 160 dxa (8pt spacing between turns)

SPACING_BREAKDOWN_CONTENT_BEFORE = Pt(2.0)
SPACING_BREAKDOWN_CONTENT_AFTER = Pt(2.0)
LINE_SPACING_BREAKDOWN = 1.15  # 276 dxa
LINE_SPACING_ACTION_ITEMS = 1.2  # 288 dxa

# ---------------------------------------------------------------------------
# Table Geometry & Cell Padding (top, bottom, left, right in dxa)
# ---------------------------------------------------------------------------
TABLE_METRICS_COL_WIDTHS = (2592, 2304, 2592, 2304)  # 4 columns total 9792 dxa
PADDING_METRICS_HEADER = (100, 100, 120, 120)
PADDING_METRICS_DATA = (80, 80, 120, 120)
PADDING_BREAKDOWN_CELL = (120, 120, 160, 160)
PADDING_QA_QUESTION = (80, 80, 120, 120)
PADDING_QA_ANSWER = (100, 100, 120, 120)
PADDING_ACTION_ITEMS = (140, 140, 160, 160)

# ---------------------------------------------------------------------------
# Exact Headings and Text Labels (Matching Reference Ground Truth)
# ---------------------------------------------------------------------------
HEADER_SUBTITLE = "RESEARCH ASSISTANT • AI SYNTHESIS REPORT"

HEADING_SECTION_1 = "1. Document Metrics & Credibility Assessment"
HEADING_SECTION_2 = "2. Executive Research Breakdown"
HEADING_SECTION_3 = "3. Paper Q&A Assistant Dialogue Transcript"
HEADING_SECTION_4 = "4. Researcher Annotations & Follow-Up Actions"

TABLE_METRICS_HEADERS = ["Document Attribute", "Value", "Credibility Signal", "Status"]

# Ground truth labels from reference file Table 1
LABEL_ATTR_FILE = "File Name"
LABEL_ATTR_LENGTH = "Total Length"
LABEL_ATTR_STATUS = "Processing Status"
LABEL_ATTR_DOMAIN = "Academic Domain"

LABEL_SIG_VENUE = "Venue Verification"
LABEL_SIG_REFERENCES = "References Analyzed"
LABEL_SIG_CITATIONS = "Citations Baseline"
LABEL_SIG_SCORE = "Reporting Signals Score"

# Five Executive Breakdown blocks with square markers (■  )
BREAKDOWN_BLOCKS = [
    ("■  TITLE, AUTHORS & ABSTRACT", "title_authors_abstract"),
    ("■  PROBLEM STATEMENT", "problem_statement"),
    ("■  METHODOLOGY", "methodology"),
    ("■  KEY RESULTS", "key_results"),
    ("■  CONCLUSION & RECOMMENDATIONS", "conclusion"),
]

LABEL_YOUR_NOTES = "Your notes"
TITLE_ACTION_ITEMS = "📌 Key Action Items for Further Review:"

FOOTER_DISCLAIMER_TEXT = (
    "This report reflects the uploaded paper and reporting signals. "
    "It does not verify research quality."
)
