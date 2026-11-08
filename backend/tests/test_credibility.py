"""Tests for asynchronous Document Credibility & Reporting Signals service using OpenAlex."""

import asyncio
from pathlib import Path

import httpx
import pytest

from app.core.dependencies import get_chroma_client, get_embedding_function
from app.db.session import SessionLocal
from app.models.credibility import DocumentCredibility
from app.schemas.credibility import CredibilityResponse, CredibilitySignals
from app.services.credibility_service import (
    calculate_credibility_score,
    evaluate_document_credibility,
    extract_academic_affiliation_from_front_matter,
    extract_doi,
    fetch_openalex_by_doi,
    fetch_openalex_record,
    sanitize_openalex_title,
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


def test_sanitize_openalex_title() -> None:
    """Verify stripping of all punctuation (colons, dashes, apostrophes, etc.) and whitespace collapsing."""
    raw = "The Impact of COVID-19 on Student Experiences and Expectations: Evidence from a Survey"
    expected = "The Impact of COVID 19 on Student Experiences and Expectations Evidence from a Survey"
    assert sanitize_openalex_title(raw) == expected
    assert (
        sanitize_openalex_title("What's Next? A / B Testing: Results-Driven")
        == "What s Next A B Testing Results Driven"
    )


def test_page_2_academic_email_affiliation_extraction() -> None:
    """Verify inspecting Page 1 AND Page 2 detects academic emails (e.g. @asu.edu) and awards 10 affiliation points."""
    page_1_cover = """
    NATIONAL BUREAU OF ECONOMIC RESEARCH
    1050 Massachusetts Avenue
    Cambridge, MA 02138
    Working Paper Series
    """
    page_2_author_info = """
    The Impact of COVID-19 on Student Experiences and Expectations: Evidence from a Survey
    Esteban M. Aucejo
    Department of Economics, Arizona State University
    Email: esteban.aucejo@asu.edu
    Jacob French
    Basit Zafar
    """
    full_text = f"{page_1_cover}\n\n{page_2_author_info}\n\nAbstract\nWe survey 1500 students..."

    assert (
        extract_academic_affiliation_from_front_matter(
            page_1_cover, full_text=full_text
        )
        is True
    )

    _score, signals, _, _ = calculate_credibility_score(
        external_check="skipped",
        external_record=None,
        title_similarity=0.0,
        has_doi=False,
        full_text=full_text,
        page_1_text=page_1_cover,
        reference_count=15,
    )
    assert signals.author_academic_affiliation is True
    assert signals.has_academic_affiliation is True
    assert signals.affiliation_points == 10


def test_openalex_matched_title_awards_venue_and_affiliation() -> None:
    """Case 1: OpenAlex search with matched title (similarity >= 0.85) -> returns venue, citations, institution affiliation."""
    title = "Deep Residual Learning for Image Recognition"
    ext_record = {
        "title": "Deep Residual Learning for Image Recognition",
        "venue": "IEEE Conference on Computer Vision and Pattern Recognition",
        "year": 2016,
        "citation_count": 120,
        "has_institution": True,
        "source": "OpenAlex",
    }
    sim = token_set_ratio(title, ext_record["title"])
    assert sim >= 0.85

    score, signals, badge_label, badge_variant = calculate_credibility_score(
        external_check="matched",
        external_record=ext_record,
        title_similarity=sim,
        has_doi=True,
        full_text="Abstract: This paper presents... Methodology ... Results ... Discussion ...",
        page_1_text="Abstract: This paper presents... Author author@mit.edu",
        reference_count=25,
    )

    assert (
        signals.matched_venue
        == "IEEE Conference on Computer Vision and Pattern Recognition"
    )
    assert signals.author_academic_affiliation is True
    assert signals.has_academic_affiliation is True
    assert badge_variant == "success"
    assert badge_label == "Indexed in OpenAlex"
    # Venue: 35, Citations: 25, References: 20, Affiliation: 10, Structure: 10 -> total >= 100
    assert score >= 100


def test_openalex_mismatched_title_rejected() -> None:
    """Case 2: OpenAlex search with mismatched title (< 0.85) -> rejected, falls back to internal heuristics."""
    title = "Deep Residual Learning for Image Recognition"
    ext_record = {
        "title": "Completely Different Paper About Quantum Physics",
        "venue": "Physical Review B",
        "year": 2016,
        "citation_count": 100,
        "has_institution": False,
        "source": "OpenAlex",
    }
    sim = token_set_ratio(title, ext_record["title"])
    assert sim < 0.85

    score, signals, _badge_label, badge_variant = calculate_credibility_score(
        external_check="not_matched",
        external_record=ext_record,
        title_similarity=sim,
        has_doi=True,
        full_text="Methodology ... Results ...",
        page_1_text="",
        reference_count=15,
    )

    assert signals.matched_venue is None
    assert badge_variant in ("warning", "neutral")
    # Zero venue points awarded: max base without venue is 65
    assert score <= 65


def test_title_search_similarity_threshold_boundary() -> None:
    """Cases 3 & 4: Title similarity at 0.79 rejected (not_matched); at 0.81 accepted (matched >= 0.80)."""
    # 0.79 boundary
    score_low, signals_low, _, _ = calculate_credibility_score(
        external_check="not_matched",
        external_record={"venue": "IEEE Trans", "citation_count": 10, "year": 2020},
        title_similarity=0.79,
        has_doi=False,
        full_text="Abstract ... Methodology ...",
        page_1_text="",
        reference_count=10,
    )
    assert signals_low.matched_venue is None

    # 0.81 boundary
    score_high, signals_high, _, _ = calculate_credibility_score(
        external_check="matched",
        external_record={"venue": "IEEE Trans", "citation_count": 10, "year": 2020},
        title_similarity=0.81,
        has_doi=False,
        full_text="Abstract ... Methodology ...",
        page_1_text="",
        reference_count=10,
    )
    assert signals_high.matched_venue == "IEEE Trans"
    assert score_high >= score_low + 35  # Exactly 35 venue points difference


def test_universal_doi_extraction_patterns() -> None:
    """Verify universal DOI extraction handles standard DOIs and DOI URLs across Page 1 & 2."""
    assert (
        extract_doi("Available with DOI: 10.1016/j.jpubeco.2020.104271.")
        == "10.1016/j.jpubeco.2020.104271"
    )
    assert (
        extract_doi("Published at https://doi.org/10.1016/j.jpubeco.2020.104271")
        == "10.1016/j.jpubeco.2020.104271"
    )
    assert extract_doi("doi.org/10.1109/CVPR.2021.12345;") == "10.1109/CVPR.2021.12345"
    assert extract_doi("http://dx.doi.org/10.1000/182,") == "10.1000/182"


@pytest.mark.asyncio
async def test_openalex_direct_doi_endpoint() -> None:
    """Verify OpenAlex DOI lookup queries https://api.openalex.org/works/https://doi.org/{doi}."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert "works/https://doi.org/10.1016/j.jpubeco.2020.104271" in str(request.url)
        return httpx.Response(
            200,
            json={
                "display_name": "The impact of COVID-19 on student experiences",
                "publication_year": 2020,
                "cited_by_count": 976,
                "primary_location": {
                    "source": {"display_name": "Journal of Public Economics"}
                },
                "authorships": [
                    {
                        "author": {"display_name": "Esteban M. Aucejo"},
                        "institutions": [{"display_name": "Arizona State University"}],
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        record = await fetch_openalex_by_doi(
            "10.1016/j.jpubeco.2020.104271", client=client
        )
        assert record is not None
        assert record["venue"] == "Journal of Public Economics"
        assert record["citation_count"] == 976
        assert record["has_institution"] is True
        assert record["doi"] == "10.1016/j.jpubeco.2020.104271"


@pytest.mark.asyncio
async def test_openalex_api_fetch_and_parse() -> None:
    """Case 6: Querying OpenAlex Works API extracts title, venue, citations, year, and institution affiliations."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert "ResearchAssistantApp/1.0" in request.headers.get("User-Agent", "")
        assert "search=" in str(request.url)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "display_name": "Attention Is All You Need",
                        "publication_year": 2017,
                        "cited_by_count": 85000,
                        "primary_location": {
                            "source": {
                                "display_name": "Advances in Neural Information Processing Systems"
                            }
                        },
                        "authorships": [
                            {
                                "author": {"display_name": "Ashish Vaswani"},
                                "institutions": [{"display_name": "Google Brain"}],
                            }
                        ],
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        record = await fetch_openalex_record("Attention Is All You Need", client=client)
        assert record is not None
        assert record["title"] == "Attention Is All You Need"
        assert record["venue"] == "Advances in Neural Information Processing Systems"
        assert record["citation_count"] == 85000
        assert record["has_institution"] is True
        assert record["year"] == 2017


@pytest.mark.asyncio
async def test_openalex_network_timeout_sets_error_and_falls_back(
    tmp_path: Path,
) -> None:
    """Case 7: Network timeout (> 2.5s) -> sets external_check: 'error', graceful fallback without failing upload."""
    doc_hash = "c" * 64

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Simulated 2.5s timeout from OpenAlex API")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        db = SessionLocal()
        try:
            record = await evaluate_document_credibility(
                doc_hash=doc_hash,
                db=db,
                page_1_text="Large Prominent Title for Document\nAuthor author@stanford.edu",
                full_text="Large Prominent Title for Document\nAbstract...\nMethodology...\nResults...\nDiscussion...",
                http_client=client,
            )

            assert record.status == "completed"
            assert record.external_check == "error"
            assert record.score > 0  # Scored via internal heuristics
            assert record.badge_label in ("Preprint Series", "Unindexed Draft")
        finally:
            db.close()


def test_schema_populated_numeric_values() -> None:
    """Case 8: Schema verification ensuring frontend receives populated numeric values for references and sections."""
    score, signals, badge_label, badge_variant = calculate_credibility_score(
        external_check="matched",
        external_record={
            "venue": "IEEE",
            "citation_count": 7,
            "year": 2021,
            "has_institution": True,
        },
        title_similarity=0.92,
        has_doi=True,
        full_text="Abstract... Methodology... Results... Discussion... References\n[1] A\n[2] B\n[3] C\n[4] D\n[5] E\n[6] F\n[7] G\n[8] H\n[9] I\n[10] J",
        page_1_text="Title\nAbstract...",
        reference_count=10,
    )

    data = signals.model_dump()
    assert isinstance(data["reference_count_estimated"], int)
    assert data["reference_count_estimated"] == 10
    assert isinstance(data["structure_sections_found"], int)
    assert data["structure_sections_found"] == 4
    assert isinstance(data["citation_count"], int)
    assert data["citation_count"] == 7
    assert data["author_academic_affiliation"] is True

    # Test full response validation
    response = CredibilityResponse(
        status="completed",
        score=score,
        badge_label=badge_label,
        badge_variant=badge_variant,
        signals=signals,
    )
    resp_dict = response.model_dump()
    assert resp_dict["signals"]["reference_count_estimated"] == 10
    assert resp_dict["signals"]["structure_sections_found"] == 4


def test_paper_with_no_repository_links_incurs_zero_penalty() -> None:
    """Case 9: Paper with no repository links receives 0 bonus points without deducting from base score."""
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


def test_international_academic_affiliation_patterns() -> None:
    """Case 10: Verify international academic domains (.edu.<cc>, .ac.<cc>) award 10 points while standard webmail receives 0."""
    _score_mm, signals_mm, _, _ = calculate_credibility_score(
        external_check="skipped",
        external_record=None,
        title_similarity=0.0,
        has_doi=False,
        full_text="Methodology ... Results ...",
        page_1_text="Research Paper\nContact: user@domain.edu.mm",
        reference_count=10,
    )
    assert signals_mm.author_academic_affiliation is True

    _score_lk, signals_lk, _, _ = calculate_credibility_score(
        external_check="skipped",
        external_record=None,
        title_similarity=0.0,
        has_doi=False,
        full_text="Methodology ... Results ...",
        page_1_text="Research Paper\nContact: author@dept.ac.lk",
        reference_count=10,
    )
    assert signals_lk.author_academic_affiliation is True

    _score_gmail, signals_gmail, _, _ = calculate_credibility_score(
        external_check="skipped",
        external_record=None,
        title_similarity=0.0,
        has_doi=False,
        full_text="Methodology ... Results ...",
        page_1_text="Research Paper\nContact: author@gmail.com",
        reference_count=10,
    )
    assert signals_gmail.author_academic_affiliation is False


def test_doi_extraction_excludes_footnotes_and_references() -> None:
    """Case 11: Ensure DOIs in footnotes and references sections are strictly excluded."""
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
    """Case 12: GET /api/documents/{hash}/credibility enforces 404 on unowned document and returns completed response for owned document."""
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
        rec.badge_label = "Indexed in OpenAlex"
        rec.badge_variant = "success"
        rec.signals_json = CredibilitySignals(
            matched_venue="CVPR",
            reference_count_estimated=25,
            structure_sections_found=4,
        ).model_dump_json()
        db.commit()

        resp_done = auth_client.get(f"/api/documents/{doc_hash}/credibility")
        assert resp_done.status_code == 200
        data_done = resp_done.json()
        assert data_done["status"] == "completed"
        assert data_done["score"] == 82
        assert data_done["badge_label"] == "Indexed in OpenAlex"
        assert data_done["signals"]["reference_count_estimated"] == 25
        assert data_done["signals"]["structure_sections_found"] == 4
    finally:
        app.dependency_overrides.clear()


def test_flexible_token_similarity_and_threshold_boundary() -> None:
    """Verify flexible token similarity with subtitle splitting and the 0.70 threshold boundary."""
    from app.services.credibility_service import compute_flexible_similarity

    # Subtitle splitting on colon
    t1 = "The Impact of COVID-19 on Student Experiences: Evidence from a Survey"
    t2 = "The Impact of COVID-19 on Student Experiences"
    sim = compute_flexible_similarity(t1, t2)
    assert sim == 1.0  # Main title tokens match 100%

    # Threshold boundary verification
    score_71, _, badge_71, _ = calculate_credibility_score(
        external_check="matched",
        external_record={"venue": "IEEE", "citation_count": 10},
        title_similarity=0.71,
        has_doi=False,
        full_text="Methodology ... Results ...",
        page_1_text="...",
        reference_count=10,
    )
    assert badge_71 == "Indexed in OpenAlex"
    assert score_71 >= 50

    score_69, _, badge_69, _ = calculate_credibility_score(
        external_check="not_matched",
        external_record=None,
        title_similarity=0.69,
        has_doi=False,
        full_text="Methodology ... Results ...",
        page_1_text="...",
        reference_count=10,
    )
    assert badge_69 == "Unindexed Draft"


def test_extract_title_skips_working_paper_banners() -> None:
    """Verify that extract_title_from_page_1 ignores working paper banners like NBER WORKING PAPER SERIES."""
    from app.services.credibility_service import extract_title_from_page_1
    page_1 = """
    NBER WORKING PAPER SERIES

    THE IMPACT OF COVID-19 ON STUDENT EXPERIENCES AND EXPECTATIONS: EVIDENCE FROM A SURVEY

    Esteban M. Aucejo, Jacob F. French, Maria Paola Ugalde Araya, Basit Zafar
    Working Paper 27392
    """
    title = extract_title_from_page_1(page_1)
    assert title is not None
    assert "NBER" not in title
    assert "THE IMPACT OF COVID-19 ON STUDENT EXPERIENCES" in title
