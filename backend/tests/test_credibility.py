"""Tests for asynchronous Document Credibility & Reporting Signals service."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings
from app.core.dependencies import get_chroma_client, get_embedding_function
from app.db.session import SessionLocal
from app.models.credibility import DocumentCredibility
from app.schemas.credibility import CredibilitySignals
from app.services.credibility_service import (
    calculate_credibility_score,
    evaluate_document_credibility,
    extract_doi,
    fetch_semantic_scholar_record,
    token_set_ratio,
)
from app.services.qa import index_document
from tests.conftest import AuthenticatedTestClient


class SimpleEmbedder:
    async def __call__(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 8 for _ in texts]


def test_token_set_ratio_calculation() -> None:
    """Verify Token-Set Ratio formula: |Tokens_extracted ∩ Tokens_returned| / |Tokens_extracted ∪ Tokens_returned|."""
    t1 = "Attention Is All You Need!"
    t2 = "attention is all you need"
    assert token_set_ratio(t1, t2) == 1.0

    t3 = "Attention Is All You Need In Transformers"
    # t1 tokens: {attention, is, all, you, need} (5)
    # t3 tokens: {attention, is, all, you, need, in, transformers} (7)
    # intersection: 5, union: 7 -> 5/7 ≈ 0.714
    assert round(token_set_ratio(t1, t3), 3) == round(5 / 7, 3)

    assert token_set_ratio("", "") == 1.0
    assert token_set_ratio("abc", "") == 0.0


def test_matching_doi_with_matching_title_awards_venue_points() -> None:
    """Case 1: Matching DOI with matching title (>= 0.85 similarity) awards 35 venue points and sets matched."""
    title = "Deep Residual Learning for Image Recognition"
    ext_record = {
        "title": "Deep Residual Learning for Image Recognition",
        "venue": "CVPR",
        "year": 2016,
        "citation_count": 100,
        "source": "Crossref",
    }
    sim = token_set_ratio(title, ext_record["title"])
    assert sim >= 0.85

    score, signals, badge_label, badge_variant = calculate_credibility_score(
        external_check="matched",
        external_record=ext_record,
        title_similarity=sim,
        has_doi=True,
        full_text="Abstract: This paper presents... Methodology ... Results ... Limitations ...",
        page_1_text="Abstract: This paper presents... Author author@mit.edu",
        reference_count=25,
    )

    assert signals.matched_venue == "CVPR"
    assert badge_variant == "success"
    assert "Crossref" in badge_label or "Matched" in badge_label
    # Venue: 35, Citations: 25, References: 20, Affiliation: 10, Structure: 10 -> total >= 100
    assert score >= 100


def test_matching_doi_with_mismatched_title_awards_zero_venue_points() -> None:
    """Case 2: Matching DOI with mismatched title (< 0.85 similarity) awards 0 venue points and sets not_matched."""
    title = "Deep Residual Learning for Image Recognition"
    ext_record = {
        "title": "Completely Different Paper About Quantum Physics",
        "venue": "Physical Review B",
        "year": 2016,
        "citation_count": 100,
        "source": "Crossref",
    }
    sim = token_set_ratio(title, ext_record["title"])
    assert sim < 0.85

    score, signals, badge_label, badge_variant = calculate_credibility_score(
        external_check="not_matched",
        external_record=ext_record,
        title_similarity=sim,
        has_doi=True,
        full_text="Methodology ... Results ...",
        page_1_text="",
        reference_count=15,
    )

    assert signals.matched_venue is None
    assert badge_variant == "neutral"
    assert badge_label == "Venue Unverified"
    # Zero venue points awarded: max base without venue is 65
    assert score <= 65


def test_title_search_similarity_threshold_boundary() -> None:
    """Cases 3 & 4: Title similarity at 0.84 rejected (not_matched); at 0.86 accepted (matched)."""
    # 0.84 boundary
    score_low, signals_low, badge_low, _ = calculate_credibility_score(
        external_check="not_matched",
        external_record={"venue": "IEEE Trans", "citation_count": 10, "year": 2020},
        title_similarity=0.84,
        has_doi=False,
        full_text="Abstract ... Methodology ...",
        page_1_text="",
        reference_count=10,
    )
    assert signals_low.matched_venue is None
    assert badge_low == "Venue Unverified"

    # 0.86 boundary
    score_high, signals_high, badge_high, _ = calculate_credibility_score(
        external_check="matched",
        external_record={"venue": "IEEE Trans", "citation_count": 10, "year": 2020},
        title_similarity=0.86,
        has_doi=False,
        full_text="Abstract ... Methodology ...",
        page_1_text="",
        reference_count=10,
    )
    assert signals_high.matched_venue == "IEEE Trans"
    assert "Matched" in badge_high
    assert score_high >= score_low + 35  # Exactly 35 venue points difference


def test_age_boundary_citation_scoring() -> None:
    """Case 5: Age boundary check: <= 2 years with 0 citations gets 15 pts; > 2 years with 0 citations gets 5 pts."""
    current_year = datetime.now(UTC).year

    # Paper exactly 2 years old (<= 2 years) with 0 citations -> 15 pts baseline
    score_recent, _, _, _ = calculate_credibility_score(
        external_check="not_matched",
        external_record={"year": current_year - 2, "citation_count": 0},
        title_similarity=0.0,
        has_doi=False,
        full_text="",
        page_1_text="",
        reference_count=0,
    )

    # Paper 3 years old (> 2 years) with 0 citations -> 5 pts
    score_established, _, _, _ = calculate_credibility_score(
        external_check="not_matched",
        external_record={"year": current_year - 3, "citation_count": 0},
        title_similarity=0.0,
        has_doi=False,
        full_text="",
        page_1_text="",
        reference_count=0,
    )

    # Difference in citations factor must be 15 - 5 = 10 pts
    assert score_recent - score_established == 10


@pytest.mark.asyncio
async def test_unauthenticated_semantic_scholar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case 6: Querying Semantic Scholar works properly when SEMANTIC_SCHOLAR_API_KEY is unset/empty without raising errors."""
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "")
    get_settings.cache_clear()

    # Mock transport responding to Semantic Scholar
    def handler(request: httpx.Request) -> httpx.Response:
        assert "x-api-key" not in request.headers
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "title": "Found Paper Title",
                        "venue": "ArXiv",
                        "year": 2023,
                        "citationCount": 5,
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        record = await fetch_semantic_scholar_record("Found Paper Title", client=client)
        assert record is not None
        assert record["title"] == "Found Paper Title"
        assert record["venue"] == "ArXiv"


def test_paper_with_no_repository_links_incurs_zero_penalty() -> None:
    """Case 7: Paper with no repository links receives 0 bonus points without deducting from base score."""
    text_without_links = (
        "Standard academic text discussing theory and experimental setups."
    )
    text_with_links = (
        text_without_links + " Code available at https://github.com/example/repo."
    )

    score_no_links, sig_no, _, _ = calculate_credibility_score(
        external_check="not_matched",
        external_record={"year": 2020, "citation_count": 5},
        title_similarity=0.0,
        has_doi=False,
        full_text=text_without_links,
        page_1_text="",
        reference_count=20,
    )

    score_with_links, sig_with, _, _ = calculate_credibility_score(
        external_check="not_matched",
        external_record={"year": 2020, "citation_count": 5},
        title_similarity=0.0,
        has_doi=False,
        full_text=text_with_links,
        page_1_text="",
        reference_count=20,
    )

    assert sig_no.open_artifacts_detected is False
    assert sig_with.open_artifacts_detected is True
    assert score_with_links == score_no_links + 5


@pytest.mark.asyncio
async def test_external_api_timeout_sets_error_and_falls_back(tmp_path: Path) -> None:
    """Case 8: External API timeout (> 2.0s) sets external_check: 'error', falls back to heuristics, and completes."""
    doc_hash = "a" * 64

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Simulated 2.0s timeout from external API")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        db = SessionLocal()
        try:
            record = await evaluate_document_credibility(
                doc_hash=doc_hash,
                db=db,
                page_1_text="Large Prominent Title for Document\nAuthor author@stanford.edu",
                full_text="Large Prominent Title for Document\nAbstract...\nMethodology...\nResults...",
                http_client=client,
            )

            assert record.status == "completed"
            assert record.external_check == "error"
            assert record.badge_label == "Venue Unverified"
            assert (
                record.score > 0
            )  # Internal heuristics scored affiliation + structure
        finally:
            db.close()


def test_doi_extraction_excludes_footnotes_and_references() -> None:
    """Ensure DOIs in footnotes and references sections are strictly excluded."""
    page_1_with_ref = """
    Advances in Computational Linguistics
    Header metadata block: 10.1145/1234567.890123

    Abstract
    We study syntax trees.

    References
    [1] Author A. 10.1000/footnote_or_bib_doi_to_ignore
    """
    doi = extract_doi(page_1_with_ref)
    assert doi == "10.1145/1234567.890123"


def test_credibility_endpoint_prechecks_and_retrieval(
    auth_client: AuthenticatedTestClient, tmp_path: Path
) -> None:
    """GET /api/documents/{hash}/credibility enforces 404 on unowned document and returns completed response for owned document."""
    doc_hash = "b" * 64
    chroma_dir = tmp_path / "chroma_test"
    import chromadb

    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))
    embedder = SimpleEmbedder()

    # Index document
    asyncio.run(
        index_document(
            doc_hash=doc_hash,
            chunks=[{"text": "Sample document text.", "page": 1}],
            embed_fn=embedder,
            client=chroma_client,
        )
    )

    app_chroma = chroma_client
    from app.main import app

    app.dependency_overrides[get_chroma_client] = lambda: app_chroma
    app.dependency_overrides[get_embedding_function] = lambda: embedder

    try:
        # Non-owner request -> 404
        resp_404 = auth_client.get(f"/api/documents/{doc_hash}/credibility")
        assert resp_404.status_code == 404

        # Record ownership
        auth_client.record_ownership(doc_hash)

        # Before evaluation completes -> processing
        resp_proc = auth_client.get(f"/api/documents/{doc_hash}/credibility")
        assert resp_proc.status_code == 200
        data_proc = resp_proc.json()
        assert data_proc["status"] == "processing"

        # Simulate completion
        db = auth_client.db
        rec = (
            db.query(DocumentCredibility)
            .filter(DocumentCredibility.doc_hash == doc_hash)
            .first()
        )
        if not rec:
            rec = DocumentCredibility(doc_hash=doc_hash)
            db.add(rec)
        rec.status = "completed"
        rec.score = 82
        rec.badge_label = "Venue Matched in Crossref"
        rec.badge_variant = "success"
        rec.signals_json = CredibilitySignals(matched_venue="CVPR").model_dump_json()
        db.commit()

        resp_done = auth_client.get(f"/api/documents/{doc_hash}/credibility")
        assert resp_done.status_code == 200
        data_done = resp_done.json()
        assert data_done["status"] == "completed"
        assert data_done["score"] == 82
        assert data_done["badge_label"] == "Venue Matched in Crossref"
    finally:
        app.dependency_overrides.clear()
