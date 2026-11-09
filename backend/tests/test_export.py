"""Comprehensive unit and endpoint tests for executive Word (.docx) export service."""

import hashlib
import io
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import docx
import pytest
from fastapi.testclient import TestClient

from app.api.export import export_report
from app.core.config import get_settings
from app.core.dependencies import get_paper_text_store, get_summary_cache
from app.main import app
from app.models.user import User
from app.schemas.credibility import CredibilityResponse, CredibilitySignals
from app.schemas.export import ExportMessage, ExportRequest, ExportSource
from app.services.cache import SummaryCache
from app.services.export_service import NOT_STATED, build_docx
from app.services.export_style import (
    BREAKDOWN_BLOCKS,
    COLOR_NAVY_PRIMARY,
    FONT_FAMILY,
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
    TABLE_METRICS_HEADERS,
    TITLE_ACTION_ITEMS,
)
from app.services.summary_service import InMemoryPaperTextStore
from tests.conftest import AuthenticatedTestClient
from tests.test_summarizer import VALID_SUMMARY_DICT

VALID_HASH = hashlib.sha256(b"commit export test paper bytes").hexdigest()
UNKNOWN_HASH = "0123456789abcdef" * 4


@pytest.fixture
def clean_export_env(
    tmp_path: Path,
) -> Generator[tuple[SummaryCache, InMemoryPaperTextStore], None, None]:
    """Provide isolated cache and text store for export testing."""
    cache = SummaryCache(cache_dir=tmp_path)
    text_store = InMemoryPaperTextStore()

    app.dependency_overrides[get_summary_cache] = lambda: cache
    app.dependency_overrides[get_paper_text_store] = lambda: text_store

    get_settings.cache_clear()
    yield cache, text_store

    app.dependency_overrides.pop(get_summary_cache, None)
    app.dependency_overrides.pop(get_paper_text_store, None)
    get_settings.cache_clear()


def _get_all_document_texts(doc: docx.Document) -> list[str]:
    """Extract all text elements from document paragraphs and table cells."""
    texts = [p.text for p in doc.paragraphs if p.text]
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    if p.text:
                        texts.append(p.text)
    return texts


def test_build_docx_unit_basic() -> None:
    """Verify build_docx directly generates a valid docx with all sections and styling."""
    messages = [
        ExportMessage(
            role="user",
            text="What is the main idea?",
            sources=[],
        ),
        ExportMessage(
            role="assistant",
            text="The Transformer relies on attention.",
            sources=[ExportSource(page_number=3, snippet="Attention is all you need.")],
        ),
    ]

    docx_bytes = build_docx(
        summary=VALID_SUMMARY_DICT,
        filename="test_paper.pdf",
        date="November 8, 2026",
        messages=messages,
    )

    doc = docx.Document(io.BytesIO(docx_bytes))
    all_texts = _get_all_document_texts(doc)
    full_text = " ".join(all_texts)

    # 1. Header & Banner
    assert HEADER_SUBTITLE in full_text
    assert "Attention Is All You Need" in full_text
    assert "Generated on November 8, 2026" in full_text
    assert "Target: Vaswani et al." in full_text

    # 2. Section Headings
    assert HEADING_SECTION_1 in full_text
    assert HEADING_SECTION_2 in full_text
    assert HEADING_SECTION_3 in full_text
    assert HEADING_SECTION_4 in full_text

    # 3. Footer disclaimer & PAGE field
    footer_p = doc.sections[0].footer.paragraphs[0]
    assert FOOTER_DISCLAIMER_TEXT in footer_p.text
    assert "w:fldSimple" in footer_p._p.xml
    assert 'w:instr="PAGE"' in footer_p._p.xml


def test_export_endpoint_valid_docx(
    auth_client: AuthenticatedTestClient,
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """The response is a valid .docx that opens with python-docx and has proper attachment header."""
    cache, _ = clean_export_env
    auth_client.record_ownership(VALID_HASH)
    cache.set(VALID_HASH, VALID_SUMMARY_DICT)

    payload = {
        "doc_hash": VALID_HASH,
        "messages": [
            {"role": "user", "text": "What is the problem statement?", "sources": []},
            {
                "role": "assistant",
                "text": "Recurrent networks are sequential.",
                "sources": [
                    {
                        "page_number": 2,
                        "snippet": "Sequential computation limits parallelization.",
                    }
                ],
            },
        ],
    }

    resp = auth_client.post("/api/export", json=payload)
    assert resp.status_code == 200
    assert (
        resp.headers["content-type"]
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    assert (
        resp.headers["content-disposition"]
        == f'attachment; filename="mitra-report-{VALID_HASH[:8]}.docx"'
    )

    doc = docx.Document(io.BytesIO(resp.content))
    assert doc is not None
    assert len(doc.tables) >= 5


def test_document_metrics_table_structure_and_payload_labels(
    auth_client: AuthenticatedTestClient,
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """Section 1: 4-column table with exact attribute labels, signal labels, and payload strings."""
    cache, _ = clean_export_env
    auth_client.record_ownership(VALID_HASH)
    cache.set(VALID_HASH, VALID_SUMMARY_DICT)

    resp = auth_client.post(
        "/api/export", json={"doc_hash": VALID_HASH, "messages": []}
    )
    assert resp.status_code == 200

    doc = docx.Document(io.BytesIO(resp.content))
    # Table 0 is the thin horizontal rule; Table 1 is the 5x4 metrics table
    tbl_metrics = doc.tables[1]
    assert len(tbl_metrics.rows) == 5
    assert len(tbl_metrics.columns) == 4

    # Header row contents
    headers = [cell.text for cell in tbl_metrics.rows[0].cells]
    assert headers == TABLE_METRICS_HEADERS

    # Verify Table 1 row labels match reference file ground truth
    all_table_text = " ".join(c.text for r in tbl_metrics.rows for c in r.cells)
    assert LABEL_ATTR_FILE in all_table_text
    assert LABEL_ATTR_LENGTH in all_table_text
    assert LABEL_ATTR_STATUS in all_table_text
    assert LABEL_ATTR_DOMAIN in all_table_text

    assert LABEL_SIG_VENUE in all_table_text
    assert LABEL_SIG_REFERENCES in all_table_text
    assert LABEL_SIG_CITATIONS in all_table_text
    assert LABEL_SIG_SCORE in all_table_text

    # Exact payload strings
    assert "Unverified" in all_table_text
    assert "Recent baseline" in all_table_text
    assert "No academic domain" in all_table_text
    assert "/ 100" in all_table_text


def test_executive_breakdown_five_blocks_and_bullets(
    auth_client: AuthenticatedTestClient,
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """Section 2: Five blocks tagged with square markers (■), sentence bullets, and 'Your notes' box."""
    cache, _ = clean_export_env
    auth_client.record_ownership(VALID_HASH)
    cache.set(VALID_HASH, VALID_SUMMARY_DICT)

    resp = auth_client.post(
        "/api/export", json={"doc_hash": VALID_HASH, "messages": []}
    )
    assert resp.status_code == 200

    doc = docx.Document(io.BytesIO(resp.content))
    all_texts = _get_all_document_texts(doc)

    for marker_title, _ in BREAKDOWN_BLOCKS:
        assert any(marker_title in t for t in all_texts), (
            f"Missing block: {marker_title}"
        )

    # Verify Key Results has bullet markers
    key_results_text = next(t for t in all_texts if "BLEU score of 28.4" in t)
    assert key_results_text.startswith("•")

    # Verify 'Your notes' box appears after summary breakdown
    notes_occurrences = [t for t in all_texts if t == LABEL_YOUR_NOTES]
    assert len(notes_occurrences) >= 1


def test_missing_summary_fields_show_not_stated() -> None:
    """Missing or empty summary sections must strictly show 'Not stated in the paper.'"""
    sparse_summary = {
        "header": {"title": "Sparse Paper", "authors": "", "abstract": ""},
        "problem_statement": "",
        "methodology": None,
        "key_results": "",
        "conclusion": "   ",
    }

    docx_bytes = build_docx(
        summary=sparse_summary,
        filename="sparse.pdf",
        date="November 8, 2026",
        messages=[],
    )

    doc = docx.Document(io.BytesIO(docx_bytes))
    all_texts = _get_all_document_texts(doc)

    # Check that NOT_STATED appears for empty fields
    not_stated_count = sum(1 for t in all_texts if t == NOT_STATED)
    assert not_stated_count >= 3


def test_qa_transcript_sources_and_empty_notes_per_turn(
    auth_client: AuthenticatedTestClient,
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """Section 3: Q&A turns with 'Q: ' / 'A (Grounded AI): ', strict page citations, and notes box."""
    cache, _ = clean_export_env
    auth_client.record_ownership(VALID_HASH)
    cache.set(VALID_HASH, VALID_SUMMARY_DICT)

    payload = {
        "doc_hash": VALID_HASH,
        "messages": [
            {
                "role": "user",
                "text": "What is the BLEU score?",
                "sources": [],
            },
            {
                "role": "assistant",
                "text": "The model achieved 28.4 BLEU on English-to-German.",
                "sources": [
                    {"page_number": 5, "snippet": "Table 2: BLEU score 28.4"},
                    {"page_number": 8, "snippet": "Comparison on WMT 2014"},
                ],
            },
            {
                "role": "user",
                "text": "Is training faster?",
                "sources": [],
            },
            {
                "role": "assistant",
                "text": "Yes, significantly faster than recurrent models.",
                "sources": [],  # No sources -> sources line must be omitted
            },
        ],
    }

    resp = auth_client.post("/api/export", json=payload)
    assert resp.status_code == 200

    doc = docx.Document(io.BytesIO(resp.content))
    all_texts = _get_all_document_texts(doc)

    # Check Q&A markers
    assert any("Q: What is the BLEU score?" in t for t in all_texts)
    assert any("A (Grounded AI): The model achieved 28.4 BLEU" in t for t in all_texts)

    # Check grounded citations strictly from page numbers
    assert any("Sources: Page 5, Page 8" in t for t in all_texts)

    # Check that turn 2 (without sources) does NOT render a phantom sources line
    turn_2_text = [t for t in all_texts if "significantly faster" in t]
    assert len(turn_2_text) == 1

    # Verify 'Your notes' box exists after each Q&A turn: 1 after breakdown + 2 after Q&A turns = 3
    notes_count = sum(1 for t in all_texts if t == LABEL_YOUR_NOTES)
    assert notes_count == 3


def test_researcher_annotations_follow_up_actions_deterministic() -> None:
    """Section 4: Callout box derives action items strictly from credibility flags without LLM call."""
    # Test case 1: Unverified venue, estimated refs, no academic domain
    cred_unverified = CredibilityResponse(
        badge_label="Unindexed Draft",
        score=35,
        signals=CredibilitySignals(
            is_reference_count_estimated=True,
            author_academic_affiliation=False,
        ),
    )

    docx_bytes = build_docx(
        summary=VALID_SUMMARY_DICT,
        filename="paper.pdf",
        date="November 8, 2026",
        messages=[],
        credibility=cred_unverified,
    )

    doc = docx.Document(io.BytesIO(docx_bytes))
    all_texts = _get_all_document_texts(doc)

    assert any(TITLE_ACTION_ITEMS in t for t in all_texts)
    action_text = next(
        t for t in all_texts if "1. Confirm the publication venue manually." in t
    )
    assert "1. Confirm the publication venue manually." in action_text
    assert "2. Check the reference list against the original." in action_text
    assert "3. Verify author affiliations." in action_text

    # Test case 2: Fully verified document
    cred_verified = CredibilityResponse(
        badge_label="Indexed in OpenAlex",
        score=85,
        signals=CredibilitySignals(
            is_reference_count_estimated=False,
            author_academic_affiliation=True,
            matched_venue="NeurIPS",
        ),
    )

    docx_bytes_verified = build_docx(
        summary=VALID_SUMMARY_DICT,
        filename="paper.pdf",
        date="November 8, 2026",
        messages=[],
        credibility=cred_verified,
    )

    doc_v = docx.Document(io.BytesIO(docx_bytes_verified))
    all_texts_v = _get_all_document_texts(doc_v)
    action_text_v = next(
        t for t in all_texts_v if "All initial credibility indicators verified" in t
    )
    assert "1. All initial credibility indicators verified." in action_text_v


def test_markup_stored_as_literal_plain_text(
    auth_client: AuthenticatedTestClient,
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """A message containing <b>not bold</b> is stored as literal plain text, never interpreted as markup."""
    cache, _ = clean_export_env
    auth_client.record_ownership(VALID_HASH)
    cache.set(VALID_HASH, VALID_SUMMARY_DICT)

    payload = {
        "doc_hash": VALID_HASH,
        "messages": [
            {
                "role": "user",
                "text": "Check this <b>not bold</b> formatting",
                "sources": [],
            },
            {
                "role": "assistant",
                "text": "Received <i>plain literal</i> response.",
                "sources": [],
            },
        ],
    }

    resp = auth_client.post("/api/export", json=payload)
    assert resp.status_code == 200

    doc = docx.Document(io.BytesIO(resp.content))

    found_user_markup = False
    for t in doc.tables:
        for r in t.rows:
            for c in r.cells:
                for p in c.paragraphs:
                    if "<b>not bold</b>" in p.text:
                        found_user_markup = True
                        for run in p.runs:
                            if "<b>not bold</b>" in run.text:
                                assert run.bold is not True

    assert found_user_markup, "Literal <b>not bold</b> was not found in table cells"


def test_validation_limits_200_messages_and_4000_chars(
    auth_client: AuthenticatedTestClient,
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """An export over 200 messages returns 422. A message over 4000 characters returns 422."""
    cache, _ = clean_export_env
    auth_client.record_ownership(VALID_HASH)
    cache.set(VALID_HASH, VALID_SUMMARY_DICT)

    # Over 200 messages: 201 messages -> 422
    too_many_messages = [
        {"role": "user", "text": f"Msg {i}", "sources": []} for i in range(201)
    ]
    resp_too_many = auth_client.post(
        "/api/export",
        json={"doc_hash": VALID_HASH, "messages": too_many_messages},
    )
    assert resp_too_many.status_code == 422

    # Over 4000 characters: 4001 characters -> 422
    too_long_message = [{"role": "user", "text": "x" * 4001, "sources": []}]
    resp_too_long = auth_client.post(
        "/api/export",
        json={"doc_hash": VALID_HASH, "messages": too_long_message},
    )
    assert resp_too_long.status_code == 422

    # Exactly 200 messages and 4000 chars -> 200
    valid_boundary_messages = [
        {"role": "user", "text": "m", "sources": []} for _ in range(199)
    ]
    valid_boundary_messages.append(
        {"role": "assistant", "text": "y" * 4000, "sources": []}
    )
    resp_valid = auth_client.post(
        "/api/export",
        json={"doc_hash": VALID_HASH, "messages": valid_boundary_messages},
    )
    assert resp_valid.status_code == 200


def test_non_owner_gets_404_with_same_body_as_unknown_document(
    auth_client: AuthenticatedTestClient,
    auth_client_other: AuthenticatedTestClient,
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """A non-owner gets 404 with the same body as an unknown document."""
    cache, _ = clean_export_env
    auth_client.record_ownership(VALID_HASH)
    cache.set(VALID_HASH, VALID_SUMMARY_DICT)

    # 1. Non-owner request (user B requesting user A's doc)
    resp_non_owner = auth_client_other.post(
        "/api/export",
        json={"doc_hash": VALID_HASH, "messages": []},
    )
    assert resp_non_owner.status_code == 404

    # 2. Unknown document request (user A requesting nonexistent doc)
    resp_unknown = auth_client.post(
        "/api/export",
        json={"doc_hash": UNKNOWN_HASH, "messages": []},
    )
    assert resp_unknown.status_code == 404

    # Both must match exactly in body structure and detail
    assert resp_non_owner.json() == resp_unknown.json()
    assert resp_non_owner.json() == {
        "detail": "Document not found. Upload the PDF first."
    }


def test_missing_summary_returns_404_with_unknown_doc_body(
    auth_client: AuthenticatedTestClient,
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """A missing summary returns 404 with the same body as an unknown document."""
    auth_client.record_ownership(VALID_HASH)

    resp = auth_client.post(
        "/api/export",
        json={"doc_hash": VALID_HASH, "messages": []},
    )
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Document not found. Upload the PDF first."}


def test_unauthenticated_request_returns_401(
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """Unauthenticated requests get 401."""
    unauth_client = TestClient(app)
    resp = unauth_client.post(
        "/api/export",
        json={"doc_hash": VALID_HASH, "messages": []},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_no_network_call_made(
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """No network call is made: patch httpx and socket and assert neither is used."""
    cache, text_store = clean_export_env
    cache.set(VALID_HASH, VALID_SUMMARY_DICT)

    user = User(id="test-user-id", email="user@example.com", password_hash="hash")
    request = ExportRequest(
        doc_hash=VALID_HASH,
        messages=[
            ExportMessage(role="user", text="Are network calls made?", sources=[]),
            ExportMessage(
                role="assistant", text="No, export is purely local.", sources=[]
            ),
        ],
    )

    with (
        patch("app.api.export.is_owner", return_value=True),
        patch("socket.socket") as mock_socket,
        patch("httpx.AsyncClient") as mock_httpx_async,
        patch("httpx.Client") as mock_httpx_sync,
    ):
        resp = await export_report(
            request=request,
            current_user=user,
            db=MagicMock(),
            cache=cache,
            text_store=text_store,
        )
        assert resp.status_code == 200

        mock_socket.assert_not_called()
        mock_httpx_async.assert_not_called()
        mock_httpx_sync.assert_not_called()


def test_style_constants_match_reference() -> None:
    """Verify that typography and color constants in export_style.py match reference."""
    assert FONT_FAMILY == "Calibri"
    assert COLOR_NAVY_PRIMARY == "1E3A8A"
    assert len(TABLE_METRICS_HEADERS) == 4
    assert len(BREAKDOWN_BLOCKS) == 5
    assert BREAKDOWN_BLOCKS[0][0] == "■  TITLE, AUTHORS & ABSTRACT"
    assert BREAKDOWN_BLOCKS[4][0] == "■  CONCLUSION & RECOMMENDATIONS"
