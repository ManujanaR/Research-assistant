"""Asynchronous Document Credibility & Reporting Signals Service using OpenAlex."""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.models.credibility import DocumentCredibility
from app.schemas.credibility import CredibilitySignals
from app.services.credibility_cache import CredibilityCache

logger = logging.getLogger(__name__)

# Strict 2.5s timeout for OpenAlex API requests
OPENALEX_TIMEOUT_SECONDS = 2.5
EXTERNAL_API_TIMEOUT_SECONDS = 2.5

# Regex patterns
DOI_REGEX = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
ARXIV_REGEX = re.compile(r"\barXiv:\d{4}\.\d{4,5}\b", re.IGNORECASE)
# International second-level academic and research domains:
# Recognizes .edu, .edu.<country_code> (e.g. yeeyeemon@ucsm.edu.mm),
# .ac, .ac.<country_code> (e.g. author@dept.ac.lk, .ac.uk),
# and .gov, .gov.<country_code>.
# Note: This verifies domain pattern shape, not institutional authentication.
ACADEMIC_DOMAIN_REGEX = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.(?:edu(?:\.[a-z]{2,3})?|ac(?:\.[a-z]{2,3})?|gov(?:\.[a-z]{2,3})?)\b|"
    r"\b(?:[a-zA-Z0-9-]+\.)+(?:edu(?:\.[a-z]{2,3})?|ac(?:\.[a-z]{2,3})?|gov(?:\.[a-z]{2,3})?)\b",
    re.IGNORECASE,
)
OPEN_ARTIFACTS_REGEX = re.compile(
    r"\b(?:https?://)?(?:www\.)?(?:github\.com|gitlab\.com|zenodo\.org|figshare\.com|osf\.io|huggingface\.co|kaggle\.com)/[A-Za-z0-9_\-./]+",
    re.IGNORECASE,
)

_credibility_cache: CredibilityCache | None = None


def get_credibility_cache() -> CredibilityCache:
    """Return singleton CredibilityCache instance."""
    global _credibility_cache
    if _credibility_cache is None:
        _credibility_cache = CredibilityCache()
    return _credibility_cache


def normalize_string(text: str) -> str:
    """Convert string to lowercase, strip all punctuation ([^\\w\\s]), and collapse whitespace."""
    if not text:
        return ""
    no_punct = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(no_punct.split())


def token_set_ratio(str1: str, str2: str) -> float:
    """Calculate Token-Set Ratio: |Tokens_extracted ∩ Tokens_returned| / |Tokens_extracted ∪ Tokens_returned|."""
    norm1 = normalize_string(str1)
    norm2 = normalize_string(str2)
    tokens1 = set(norm1.split())
    tokens2 = set(norm2.split())

    if not tokens1 and not tokens2:
        return 1.0
    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    return len(intersection) / len(union)


def extract_title_from_page_1(page_1_text: str) -> str | None:
    """Extract Title strictly from the first large text block on page 1."""
    if not page_1_text:
        return None

    paragraphs = [p.strip() for p in page_1_text.split("\n\n") if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [p.strip() for p in page_1_text.splitlines() if p.strip()]

    # Skip boilerplate header tokens like arXiv / DOI / ISSN / dates
    skip_patterns = [
        re.compile(
            r"^(arxiv|doi|issn|isbn|vol\.|volume|issue|journal|proceedings|page|\d+)",
            re.IGNORECASE,
        ),
        re.compile(r"^published\s+(in|online|as)", re.IGNORECASE),
    ]

    for p in paragraphs:
        first_line = p.splitlines()[0].strip()
        if any(sp.match(first_line) for sp in skip_patterns):
            continue
        cleaned = " ".join(p.split())
        # First prominent text block of substantive length
        if len(cleaned) >= 12 and not cleaned.isdigit():
            lines = [line.strip() for line in p.splitlines() if line.strip()]
            candidate = " ".join(lines[:3]) if len(lines) > 1 else lines[0]
            return candidate[:250].strip()

    return None


def extract_doi(page_1_text: str) -> str | None:
    """Scan strictly for DOI in the page 1 header, footer, or metadata block.

    Explicitly excludes DOIs inside footnotes or references/bibliography.
    """
    if not page_1_text:
        return None

    ref_idx = -1
    for match in re.finditer(
        r"\b(references|bibliography|works cited)\b", page_1_text, re.IGNORECASE
    ):
        ref_idx = match.start()
        break

    target_text = page_1_text[:ref_idx] if ref_idx != -1 else page_1_text
    lines = target_text.splitlines()

    n = len(lines)
    header_lines = lines[: max(5, int(n * 0.3))]
    footer_lines = lines[max(0, int(n * 0.8)) :]

    candidate_lines = header_lines + footer_lines

    for line in lines:
        if re.search(r"\bdoi\b", line, re.IGNORECASE) and line not in candidate_lines:
            candidate_lines.append(line)

    for line in candidate_lines:
        if re.match(
            r"^[\*†‡\d]+\s*(author|correspondence|electronic address)",
            line,
            re.IGNORECASE,
        ):
            continue
        match = DOI_REGEX.search(line)
        if match:
            doi = match.group(0).rstrip(".,;")
            return doi

    return None


def extract_arxiv_id(page_1_text: str) -> str | None:
    """Scan for arXiv identifier on page 1."""
    if not page_1_text:
        return None
    match = ARXIV_REGEX.search(page_1_text)
    if match:
        return match.group(0).strip()
    return None


async def fetch_openalex_record(
    title: str, client: httpx.AsyncClient | None = None
) -> dict[str, Any] | None:
    """Query OpenAlex Works API for a given paper title with a strict 2.5s timeout.

    Privacy & Grounding Constraints:
    - Queries STRICTLY the clean title string. Document body, chunks, user identity,
      and chat turns are never sent.
    """
    clean_title = normalize_string(title)
    if not clean_title:
        return None

    cache = get_credibility_cache()
    cache_key = f"cred:openalex:{clean_title}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = "https://api.openalex.org/works"
    params = {
        "filter": f"title.search:{clean_title}",
        "per-page": "1",
    }
    headers = {
        "User-Agent": "ResearchAssistantApp/1.0 (mailto:support@local.app)",
        "Accept": "application/json",
    }

    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=OPENALEX_TIMEOUT_SECONDS)
        close_client = True

    try:
        resp = await client.get(url, params=params, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", [])
            # If title.search returns empty, fallback to search parameter
            if not results:
                resp_fallback = await client.get(
                    url,
                    params={"search": clean_title, "per-page": "1"},
                    headers=headers,
                )
                if resp_fallback.status_code == 200:
                    results = resp_fallback.json().get("results", [])

            if results and isinstance(results, list):
                item = results[0]
                found_title = item.get("display_name") or item.get("title") or ""

                # Venue / Source
                primary_loc = item.get("primary_location") or {}
                source_obj = primary_loc.get("source") or {}
                venue = source_obj.get("display_name") or ""
                if not venue:
                    host_venue = item.get("host_venue") or {}
                    venue = (
                        host_venue.get("display_name") or host_venue.get("name") or ""
                    )

                # Citation Count
                citation_count = int(item.get("cited_by_count", 0) or 0)

                # Affiliations: Extract authorships[].institutions[].display_name
                has_institution = False
                for authorship in item.get("authorships", []):
                    for inst in authorship.get("institutions", []):
                        if inst.get("display_name"):
                            has_institution = True
                            break
                    if has_institution:
                        break

                pub_year = item.get("publication_year")

                item_doi = item.get("doi")
                if item_doi and item_doi.startswith("https://doi.org/"):
                    item_doi = item_doi[len("https://doi.org/") :]

                record = {
                    "title": found_title,
                    "venue": venue,
                    "year": pub_year,
                    "citation_count": citation_count,
                    "has_institution": has_institution,
                    "doi": item_doi,
                    "source": "OpenAlex",
                }
                cache.set(cache_key, record)
                return record
            return None
        elif resp.status_code == 404:
            return None
    except Exception as exc:
        logger.warning("OpenAlex API request failed (%s)", type(exc).__name__)
        raise
    finally:
        if close_client:
            await client.aclose()

    return None


def estimate_references_count(full_text: str) -> int:
    """Estimate reference count from bibliography section text."""
    if not full_text:
        return 0

    ref_matches = list(
        re.finditer(
            r"\b(references|bibliography|works cited)\b", full_text, re.IGNORECASE
        )
    )
    if not ref_matches:
        return 0

    bib_text = full_text[ref_matches[-1].start() :]

    # Count bracketed numbers: [1], [2], etc.
    bracketed = re.findall(r"\[\d{1,3}\]", bib_text)
    if len(bracketed) >= 5:
        nums = [int(m.strip("[]")) for m in bracketed if m.strip("[]").isdigit()]
        if nums:
            return max(len(set(nums)), min(max(nums), len(bracketed)))

    # Count numbered list items: 1. Author, 2. Author
    numbered = re.findall(r"^\s*\d{1,3}\.\s+[A-Z]", bib_text, re.MULTILINE)
    if len(numbered) >= 5:
        return len(numbered)

    # Count lines with year patterns in parentheses: (1998), (2020)
    year_entries = re.findall(r"\((?:19|20)\d{2}[a-z]?\)", bib_text)
    if len(year_entries) >= 5:
        return len(year_entries)

    lines = [ln.strip() for ln in bib_text.splitlines() if len(ln.strip()) > 30]
    return max(0, len(lines) - 1)


def calculate_credibility_score(
    external_check: str,
    external_record: dict[str, Any] | None,
    title_similarity: float,
    has_doi: bool,
    full_text: str,
    page_1_text: str,
    reference_count: int,
) -> tuple[int, CredibilitySignals, str, str]:
    """Calculate the 100-point base score + 5-point bonus according to OpenAlex & reporting rules."""
    current_year = datetime.now(UTC).year

    # 1. Venue / Indexing (35 pts)
    # Confirmed record in OpenAlex with Token-Set Ratio >= 0.85
    venue_pts = 35 if external_check == "matched" else 0

    # 2. Citations (25 pts)
    citation_count = external_record.get("citation_count", 0) if external_record else 0
    pub_year = external_record.get("year") if external_record else None
    if pub_year is not None and isinstance(pub_year, int):
        age = current_year - pub_year
    else:
        age = 1  # Recent default if unknown

    if age <= 2:
        # If paper published within last 2 years: award 15 pts baseline for new work
        if citation_count >= 5:
            citation_pts = 25
        else:
            citation_pts = 15
    else:
        # Established papers: >= 5 cites = 25 pts, 1-4 cites = 15 pts, 0 cites = 5 pts
        if citation_count >= 5:
            citation_pts = 25
        elif citation_count >= 1:
            citation_pts = 15
        else:
            citation_pts = 5

    # 3. Estimated References (20 pts)
    # >= 20 entries = 20 pts, 10-19 entries = 15 pts, < 10 = 5 pts
    if reference_count >= 20:
        ref_pts = 20
    elif reference_count >= 10:
        ref_pts = 15
    else:
        ref_pts = 5

    # 4. Academic Affiliation (10 pts)
    # Confirmed via OpenAlex institutions or academic email regex (.edu, .ac.*, .gov)
    has_openalex_inst = (
        bool(external_record.get("has_institution")) if external_record else False
    )
    has_regex_affiliation = bool(ACADEMIC_DOMAIN_REGEX.search(page_1_text))
    has_academic_affiliation = has_openalex_inst or has_regex_affiliation
    affiliation_pts = 10 if has_academic_affiliation else 0

    # 5. Structural Rigor (10 pts)
    # Core sections: Abstract, Introduction, Methodology, Findings/Results, Conclusion/Discussion
    combined_text = f"{page_1_text}\n\n{full_text}"
    has_intro = bool(
        re.search(r"\b(abstract|introduction)\b", combined_text, re.IGNORECASE)
    )
    has_methodology = bool(
        re.search(
            r"\b(methodology|methods?|approach|materials and methods|materials & methods|implementation)\b",
            combined_text,
            re.IGNORECASE,
        )
    )
    has_results = bool(
        re.search(
            r"\b(results?|findings?|evaluation|analysis|experiments?)\b",
            combined_text,
            re.IGNORECASE,
        )
    )
    has_conclusion = bool(
        re.search(
            r"\b(discussion|conclusions?|limitations?|threats to validity|future work)\b",
            combined_text,
            re.IGNORECASE,
        )
    )

    structure_sections = sum([has_intro, has_methodology, has_results, has_conclusion])
    structure_pts = min(10, int(structure_sections * 2.5))

    # Base score max 100
    base_score = min(
        100, venue_pts + citation_pts + ref_pts + affiliation_pts + structure_pts
    )

    # 6. Bonus (+5 pts)
    open_artifacts_detected = bool(OPEN_ARTIFACTS_REGEX.search(full_text))
    bonus_pts = 5 if open_artifacts_detected else 0

    total_score = min(105, base_score + bonus_pts)

    matched_venue = external_record.get("venue", "") if external_record else None

    # Status Badges
    if external_check == "matched":
        badge_label = "Indexed in OpenAlex"
        badge_variant = "success"
    elif external_check == "error":
        badge_label = "Unindexed Draft"
        badge_variant = "neutral"
    else:
        # not_matched or skipped
        if matched_venue and any(
            p in matched_venue.lower()
            for p in ["arxiv", "biorxiv", "medrxiv", "preprint"]
        ):
            badge_label = "Preprint Series"
            badge_variant = "warning"
        else:
            badge_label = "Unindexed Draft"
            badge_variant = "neutral"

    signals = CredibilitySignals(
        has_doi=has_doi,
        doi=external_record.get("doi")
        if external_record and "doi" in external_record
        else None,
        matched_venue=matched_venue if external_check == "matched" else None,
        title_similarity=round(title_similarity, 2),
        citation_count=citation_count,
        reference_count_estimated=reference_count,
        is_reference_count_estimated=True,
        author_academic_affiliation=has_academic_affiliation,
        has_limitations_section=has_conclusion,
        open_artifacts_detected=open_artifacts_detected,
        structure_sections_found=structure_sections,
        venue_points=venue_pts,
        citation_points=citation_pts,
        reference_points=ref_pts,
        affiliation_points=affiliation_pts,
        structure_points=structure_pts,
        bonus_points=bonus_pts,
        estimated_references=reference_count,
        recorded_citations=citation_count,
        has_academic_affiliation=has_academic_affiliation,
    )

    return total_score, signals, badge_label, badge_variant


async def evaluate_document_credibility(
    doc_hash: str,
    db: Session,
    page_1_text: str | None = None,
    full_text: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> DocumentCredibility:
    """Asynchronously evaluate publication and reporting signals for a document using OpenAlex."""
    from app.services.qa import rebuild_text_from_chroma

    # If full text not provided, rebuild from Chroma
    if not full_text:
        full_text = rebuild_text_from_chroma(doc_hash) or ""

    if not page_1_text:
        # Approximate page 1 as first 3000 chars of full text
        page_1_text = full_text[:3000] if full_text else ""

    # Ensure DB record exists with processing state
    record = (
        db.query(DocumentCredibility)
        .filter(DocumentCredibility.doc_hash == doc_hash)
        .first()
    )
    if not record:
        record = DocumentCredibility(doc_hash=doc_hash, status="processing")
        db.add(record)
        db.commit()
        db.refresh(record)

    title = extract_title_from_page_1(page_1_text)
    if not title or len(title) < 5:
        from app.models.document import DocumentMetadata
        from app.services.qa import get_title_authors_abstract

        doc_meta = (
            db.query(DocumentMetadata)
            .filter(DocumentMetadata.doc_hash == doc_hash)
            .first()
        )
        if doc_meta and doc_meta.title:
            title = doc_meta.title
        else:
            sum_hdr = get_title_authors_abstract(doc_hash)
            if sum_hdr:
                title = sum_hdr.split("\n")[0].split(" by ")[0].strip()

    doi = extract_doi(page_1_text)

    external_check = "skipped"
    external_record: dict[str, Any] | None = None
    title_similarity = 0.0

    if not title:
        external_check = "skipped"
    else:
        try:
            external_record = await fetch_openalex_record(title, client=http_client)
            if external_record:
                ext_title = external_record.get("title", "")
                title_similarity = token_set_ratio(title, ext_title)
                if title_similarity >= 0.85:
                    external_check = "matched"
                else:
                    external_check = "not_matched"
            else:
                external_check = "not_matched"
        except (TimeoutError, httpx.TimeoutException):
            logger.warning(
                "OpenAlex API timeout (> 2.5s); falling back to internal heuristics."
            )
            external_check = "error"
            external_record = None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "OpenAlex check error (%s); falling back to internal heuristics.",
                type(exc).__name__,
            )
            external_check = "error"
            external_record = None

    ref_count = estimate_references_count(full_text)
    score, signals, badge_label, badge_variant = calculate_credibility_score(
        external_check=external_check,
        external_record=external_record,
        title_similarity=title_similarity,
        has_doi=bool(doi),
        full_text=full_text,
        page_1_text=page_1_text,
        reference_count=ref_count,
    )
    if doi and not signals.doi:
        signals.doi = doi

    record.status = "completed"
    record.external_check = external_check
    record.score = score
    record.badge_label = badge_label
    record.badge_variant = badge_variant
    record.signals_json = json.dumps(signals.model_dump())
    record.updated_at = datetime.now(UTC)

    db.commit()
    db.refresh(record)
    return record
