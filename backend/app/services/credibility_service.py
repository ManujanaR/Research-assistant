"""Asynchronous Document Credibility & Reporting Signals Service."""

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.credibility import DocumentCredibility
from app.schemas.credibility import CredibilitySignals
from app.services.credibility_cache import CredibilityCache

logger = logging.getLogger(__name__)

# Strict 2.0s timeout for external verification requests
EXTERNAL_API_TIMEOUT_SECONDS = 2.0

# Regex patterns
DOI_REGEX = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b")
ARXIV_REGEX = re.compile(r"\barXiv:\d{4}\.\d{4,5}\b", re.IGNORECASE)
ACADEMIC_DOMAIN_REGEX = re.compile(
    r"(?:@[\w\-.]+\.|\b)(?:[a-zA-Z0-9\-]+\.)*(?:edu|ac\.[a-z]{2,3}|gov)\b",
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
    if not paragraphs:
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
            # Return first line or full title block under 250 chars
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

    # Identify potential references section if on page 1
    ref_idx = -1
    for match in re.finditer(
        r"\b(references|bibliography|works cited)\b", page_1_text, re.IGNORECASE
    ):
        ref_idx = match.start()
        break

    target_text = page_1_text[:ref_idx] if ref_idx != -1 else page_1_text
    lines = target_text.splitlines()

    # Split lines into top header (first 30%), bottom footer (last 20%), or explicit DOI lines
    n = len(lines)
    header_lines = lines[: max(5, int(n * 0.3))]
    footer_lines = lines[max(0, int(n * 0.8)) :]

    candidate_lines = header_lines + footer_lines

    # Also search for lines that start with DOI metadata prefixes
    for line in lines:
        if re.search(r"\bdoi\b", line, re.IGNORECASE) and line not in candidate_lines:
            candidate_lines.append(line)

    for line in candidate_lines:
        # Critical guard: exclude lines that look like footnotes (e.g. starts with footnote numbers/asterisks and names)
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


async def fetch_crossref_record(
    doi: str, client: httpx.AsyncClient | None = None
) -> dict[str, Any] | None:
    """Query Crossref Works API for a given DOI with a strict 2.0s timeout."""
    cache = get_credibility_cache()
    cache_key = f"cred:doi:{doi.lower()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"https://api.crossref.org/works/{doi}"
    headers = {"User-Agent": "ResearchAssistant/1.0 (mailto:support@example.com)"}

    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=EXTERNAL_API_TIMEOUT_SECONDS)
        close_client = True

    try:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            msg = resp.json().get("message", {})
            title = ""
            titles = msg.get("title", [])
            if titles and isinstance(titles, list):
                title = titles[0]
            venue = ""
            venues = msg.get("container-title", [])
            if venues and isinstance(venues, list):
                venue = venues[0]
            elif msg.get("publisher"):
                venue = msg.get("publisher", "")

            # Year extraction
            year = None
            date_parts = (
                msg.get("published-print", {}).get("date-parts")
                or msg.get("published-online", {}).get("date-parts")
                or msg.get("created", {}).get("date-parts")
            )
            if date_parts and isinstance(date_parts, list) and date_parts[0]:
                year = date_parts[0][0]

            citations = int(msg.get("is-referenced-by-count", 0))

            record = {
                "title": title,
                "venue": venue,
                "year": year,
                "citation_count": citations,
                "source": "Crossref",
            }
            cache.set(cache_key, record)
            return record
        elif resp.status_code == 404:
            return None
    except Exception as exc:
        logger.warning("Crossref API request failed (%s)", type(exc).__name__)
        raise
    finally:
        if close_client:
            await client.aclose()

    return None


async def fetch_semantic_scholar_record(
    title: str, client: httpx.AsyncClient | None = None
) -> dict[str, Any] | None:
    """Query Semantic Scholar Graph API for a paper title with a strict 2.0s timeout."""
    settings = get_settings()
    cache = get_credibility_cache()
    cache_key = f"cred:title:{normalize_string(title)}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": title,
        "limit": "1",
        "fields": "title,venue,year,citationCount",
    }
    headers: dict[str, str] = {}
    if settings.semantic_scholar_api_key and settings.semantic_scholar_api_key.strip():
        headers["x-api-key"] = settings.semantic_scholar_api_key.strip()

    close_client = False
    if client is None:
        client = httpx.AsyncClient(timeout=EXTERNAL_API_TIMEOUT_SECONDS)
        close_client = True

    try:
        resp = await client.get(url, params=params, headers=headers)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            if data and isinstance(data, list):
                item = data[0]
                record = {
                    "title": item.get("title", ""),
                    "venue": item.get("venue", "") or "",
                    "year": item.get("year"),
                    "citation_count": int(item.get("citationCount", 0) or 0),
                    "source": "Semantic Scholar",
                }
                cache.set(cache_key, record)
                return record
            return None
        elif resp.status_code == 404:
            return None
    except Exception as exc:
        logger.warning("Semantic Scholar API request failed (%s)", type(exc).__name__)
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

    # Look in the text starting from the last references header
    bib_text = full_text[ref_matches[-1].start() :]

    # Count bracketed numbers: [1], [2], etc.
    bracketed = re.findall(r"\[\d{1,3}\]", bib_text)
    if len(bracketed) >= 5:
        # Return highest number or unique count
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
    """Calculate the 100-point base score + 5-point bonus according to scoring rules."""
    current_year = datetime.now(UTC).year

    # 1. Venue Match (35 pts)
    venue_pts = 35 if external_check == "matched" else 0

    # 2. Citation Factor (25 pts)
    citation_count = external_record.get("citation_count", 0) if external_record else 0
    pub_year = external_record.get("year") if external_record else None
    if pub_year is not None and isinstance(pub_year, int):
        age = current_year - pub_year
    else:
        age = 1  # Recent default if unknown

    if age <= 2:
        if citation_count >= 5:
            citation_pts = 25
        elif citation_count >= 1:
            citation_pts = 20
        else:
            citation_pts = 15  # Age-normalized baseline
    else:
        if citation_count >= 5:
            citation_pts = 25
        elif citation_count >= 1:
            citation_pts = 15
        else:
            citation_pts = 5

    # 3. Reference List Depth (20 pts)
    if reference_count >= 20:
        ref_pts = 20
    elif reference_count >= 10:
        ref_pts = 10
    else:
        ref_pts = 5

    # 4. Academic Affiliation (10 pts)
    has_academic_affiliation = bool(ACADEMIC_DOMAIN_REGEX.search(page_1_text))
    affiliation_pts = 10 if has_academic_affiliation else 0

    # 5. Structural Rigor (10 pts)
    has_abstract = bool(re.search(r"\babstract\b", page_1_text[:2000], re.IGNORECASE))
    has_methodology = bool(
        re.search(
            r"\b(methodology|methods|materials and methods)\b", full_text, re.IGNORECASE
        )
    )
    has_results = bool(
        re.search(r"\b(results|findings|evaluation)\b", full_text, re.IGNORECASE)
    )
    has_limitations = bool(
        re.search(r"\b(limitations?|threats to validity)\b", full_text, re.IGNORECASE)
    )

    structure_sections = sum(
        [has_abstract, has_methodology, has_results, has_limitations]
    )
    structure_pts = min(10, int(structure_sections * 2.5))

    # Base score max 100
    base_score = min(
        100, venue_pts + citation_pts + ref_pts + affiliation_pts + structure_pts
    )

    # 6. Bonus (+5 pts)
    open_artifacts_detected = bool(OPEN_ARTIFACTS_REGEX.search(full_text))
    bonus_pts = 5 if open_artifacts_detected else 0

    total_score = min(105, base_score + bonus_pts)

    # Badges
    matched_venue = external_record.get("venue", "") if external_record else None
    if external_check == "matched":
        source_name = (
            external_record.get("source", "Crossref") if external_record else "Crossref"
        )
        if matched_venue and any(
            p in matched_venue.lower()
            for p in ["arxiv", "biorxiv", "medrxiv", "preprint"]
        ):
            badge_label = "Preprint / Self-Archived"
            badge_variant = "warning"
        elif matched_venue:
            badge_label = f"Venue Matched in {source_name}"
            badge_variant = "success"
        else:
            badge_label = "Preprint / Self-Archived"
            badge_variant = "warning"
    else:
        badge_label = "Venue Unverified"
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
        has_limitations_section=has_limitations,
        open_artifacts_detected=open_artifacts_detected,
    )

    return total_score, signals, badge_label, badge_variant


async def evaluate_document_credibility(
    doc_hash: str,
    db: Session,
    page_1_text: str | None = None,
    full_text: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> DocumentCredibility:
    """Asynchronously evaluate publication and reporting signals for a document."""
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
    doi = extract_doi(page_1_text)
    arxiv_id = extract_arxiv_id(page_1_text)

    external_check = "skipped"
    external_record: dict[str, Any] | None = None
    title_similarity = 0.0

    if not title:
        external_check = "skipped"
    else:
        try:
            if doi:
                external_record = await fetch_crossref_record(doi, client=http_client)
                if external_record:
                    external_record["doi"] = doi
                    ext_title = external_record.get("title", "")
                    title_similarity = token_set_ratio(title, ext_title)
                    if title_similarity >= 0.85:
                        external_check = "matched"
                    else:
                        external_check = "not_matched"
                else:
                    external_check = "not_matched"
            else:
                # Query Semantic Scholar by title
                query_title = title if not arxiv_id else f"{title} {arxiv_id}"
                external_record = await fetch_semantic_scholar_record(
                    query_title, client=http_client
                )
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
                "External credibility API timeout (> 2.0s); falling back to internal heuristics."
            )
            external_check = "error"
            external_record = None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "External credibility check error (%s); falling back to internal heuristics.",
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
