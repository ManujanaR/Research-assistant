"""Tests for Word (.docx) export service and endpoint."""

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
from app.schemas.export import ExportMessage, ExportRequest, ExportSource
from app.services.cache import SummaryCache
from app.services.export_service import DISCLAIMER_TEXT, build_docx
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


def test_build_docx_unit_basic() -> None:
    """Verify build_docx directly generates a valid docx with all sections."""
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
    all_text = " ".join(p.text for p in doc.paragraphs)

    assert "Mitra Research Assistant Report" in all_text
    assert "test_paper.pdf" in all_text
    assert "November 8, 2026" in all_text
    assert doc.sections[0].footer.paragraphs[0].text == DISCLAIMER_TEXT


def test_export_endpoint_valid_docx(
    auth_client: AuthenticatedTestClient,
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """The response is a valid .docx that opens with python-docx."""
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
    assert len(doc.paragraphs) > 0


def test_file_contains_title_five_headings_and_disclaimer(
    auth_client: AuthenticatedTestClient,
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """The file contains the title, the five headings in order, and the disclaimer."""
    cache, _ = clean_export_env
    auth_client.record_ownership(VALID_HASH)
    cache.set(VALID_HASH, VALID_SUMMARY_DICT)

    payload = {
        "doc_hash": VALID_HASH,
        "messages": [],
    }

    resp = auth_client.post("/api/export", json=payload)
    assert resp.status_code == 200

    doc = docx.Document(io.BytesIO(resp.content))
    paragraph_texts = [p.text for p in doc.paragraphs]

    # Title
    assert "Mitra Research Assistant Report" in paragraph_texts[0]

    # Five headings in order
    five_headings = [
        "Title, Authors & Abstract",
        "Problem Statement",
        "Methodology",
        "Key Results",
        "Conclusion",
    ]

    last_index = -1
    for heading in five_headings:
        assert heading in paragraph_texts
        curr_index = paragraph_texts.index(heading)
        assert curr_index > last_index, f"Heading {heading} appeared out of order"
        last_index = curr_index

    # Disclaimer in footer
    footer_text = doc.sections[0].footer.paragraphs[0].text
    assert footer_text == DISCLAIMER_TEXT


def test_assistant_message_shows_sources_with_page_numbers(
    auth_client: AuthenticatedTestClient,
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """Each assistant message shows its sources with page numbers."""
    cache, _ = clean_export_env
    auth_client.record_ownership(VALID_HASH)
    cache.set(VALID_HASH, VALID_SUMMARY_DICT)

    payload = {
        "doc_hash": VALID_HASH,
        "messages": [
            {
                "role": "assistant",
                "text": "The model achieved 28.4 BLEU.",
                "sources": [
                    {
                        "page_number": 5,
                        "snippet": "BLEU score of 28.4 on English-to-German.",
                    },
                    {"page_number": 8, "snippet": "Table 2 results comparison."},
                ],
            }
        ],
    }

    resp = auth_client.post("/api/export", json=payload)
    assert resp.status_code == 200

    doc = docx.Document(io.BytesIO(resp.content))
    all_text = "\n".join(p.text for p in doc.paragraphs)

    assert "Page 5" in all_text
    assert "Page 8" in all_text
    assert "BLEU score of 28.4" in all_text


def test_my_notes_appears_after_summary_and_after_each_answer(
    auth_client: AuthenticatedTestClient,
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """'My notes' appears after the summary and after each answer, followed by an empty paragraph."""
    cache, _ = clean_export_env
    auth_client.record_ownership(VALID_HASH)
    cache.set(VALID_HASH, VALID_SUMMARY_DICT)

    payload = {
        "doc_hash": VALID_HASH,
        "messages": [
            {"role": "user", "text": "Question 1", "sources": []},
            {"role": "assistant", "text": "Answer 1", "sources": []},
            {"role": "user", "text": "Question 2", "sources": []},
            {"role": "assistant", "text": "Answer 2", "sources": []},
        ],
    }

    resp = auth_client.post("/api/export", json=payload)
    assert resp.status_code == 200

    doc = docx.Document(io.BytesIO(resp.content))
    paragraphs = doc.paragraphs

    # Count occurrences of "My notes"
    notes_indices = [i for i, p in enumerate(paragraphs) if p.text == "My notes"]
    # 1 after summary + 1 after Answer 1 + 1 after Answer 2 = 3
    assert len(notes_indices) == 3

    # Check each "My notes" is followed by an empty paragraph
    for idx in notes_indices:
        assert idx + 1 < len(paragraphs)
        assert paragraphs[idx + 1].text == ""

    # Verify first "My notes" appears after Conclusion and before Conversation
    conclusion_idx = next(i for i, p in enumerate(paragraphs) if p.text == "Conclusion")
    conversation_idx = next(
        i for i, p in enumerate(paragraphs) if p.text == "Conversation"
    )
    assert conclusion_idx < notes_indices[0] < conversation_idx

    # Verify second "My notes" appears after Answer 1
    answer1_idx = next(i for i, p in enumerate(paragraphs) if p.text == "Answer 1")
    assert answer1_idx < notes_indices[1]

    # Verify third "My notes" appears after Answer 2
    answer2_idx = next(i for i, p in enumerate(paragraphs) if p.text == "Answer 2")
    assert answer2_idx < notes_indices[2]


def test_markup_stored_as_literal_text(
    auth_client: AuthenticatedTestClient,
    clean_export_env: tuple[SummaryCache, InMemoryPaperTextStore],
) -> None:
    """A message containing <b>not bold</b> is stored as literal text, not markup."""
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

    found_user_p = False
    for p in doc.paragraphs:
        if "<b>not bold</b>" in p.text:
            found_user_p = True
            # Verify the run is literal text and NOT marked bold
            for run in p.runs:
                if "<b>not bold</b>" in run.text:
                    assert run.bold is not True

    assert found_user_p, "Literal <b>not bold</b> paragraph was not found"


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
    # Owned by auth_client, but summary is NOT in cache
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
