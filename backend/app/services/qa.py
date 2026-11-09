import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import chromadb
import openai
from chromadb.api import ClientAPI

from app.core.config import get_settings
from app.schemas.chat import ChatMessage, ChatSource
from app.services.cache import HEX_SHA256_PATTERN

logger = logging.getLogger(__name__)

EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]

FALLBACK_GROUNDING_MESSAGE = (
    "The uploaded paper does not contain information to answer this question."
)

CHAT_SYSTEM_PROMPT_TEMPLATE = """You are an authentic, intelligent, and grounded AI Research Assistant helping the user explore and understand the uploaded academic paper.

Context:
{metadata_block}

Relevant Document Excerpts:
{retrieved_chunks}

Behavioral Guidelines:
1. Conversational Banter & Casual Energy:
   - If the user uses greetings, slang, enthusiasm, or casual check-ins (e.g., "lets cook this", "hello", "bro", "ready?", "thanks"):
     * Match their energy naturally and authentically in 1-2 friendly sentences.
     * Invite them into the paper (e.g., "Let's do it! The paper is ready. Where should we begin—the core findings, methodology, or key takeaways?").
     * NEVER output robotic disclaimers or document refusal phrases for conversational turns.

2. Bibliographic & Metadata Queries:
   - If the user asks about authors, publisher, publication venue, title, or year (e.g., "who wrote this", "who publish this", "what journal"):
     * Answer directly using <DOCUMENT_METADATA>.
     * If a specific field is not present or says 'Not specified', state naturally: "The specific publisher/venue is not explicitly listed in the document's header metadata." (Do not claim the paper lacks information).

3. Empirical & Document Research Questions:
   - When the user asks factual, analytical, or scientific questions about the paper's contents, methods, data, or arguments:
     * Ground your answer strictly on <RETRIEVED_CHUNKS>.
     * If the question contains a minor spelling error and the intended concept is clearly present in the passages, answer it. Do not refuse because of the spelling.
     * ONLY if the retrieved excerpts contain zero supporting evidence or relevant information to answer the question, output strictly:
       "The uploaded paper does not contain information to answer this question."

4. Explicitly Out-of-Scope Queries:
   - If the user asks general trivia or unrelated world knowledge completely detached from academic research:
     * Politely state: "I can only answer questions about this paper. Ask me about its problem, methods, or results."
"""

SYSTEM_PROMPT = CHAT_SYSTEM_PROMPT_TEMPLATE


@dataclass
class RetrievedChunk:
    """A retrieved document chunk with page provenance and distance score."""

    text: str
    page: int
    distance: float


class EmbeddingDimensionMismatchError(ValueError):
    """Raised when query embedding dimension does not match collection embedding dimension."""


def _validate_hash(doc_hash: str) -> None:
    """Validate that doc_hash strictly conforms to the SHA-256 regex."""
    if not isinstance(doc_hash, str) or not HEX_SHA256_PATTERN.match(doc_hash):
        raise ValueError(f"Invalid SHA-256 hash: {doc_hash!r}")


def get_chroma_collection_name(doc_hash: str) -> str:
    """Return valid Chroma collection name: 'doc_' + first 32 hex chars."""
    _validate_hash(doc_hash)
    return "doc_" + doc_hash[:32]


def collection_exists(doc_hash: str, client: ClientAPI | None = None) -> bool:
    """Check if a Chroma collection exists for the given document hash."""
    _validate_hash(doc_hash)
    if client is None:
        settings = get_settings()
        client = chromadb.PersistentClient(path=settings.chroma_dir)

    collection_name = get_chroma_collection_name(doc_hash)
    try:
        client.get_collection(name=collection_name)
        return True
    except (chromadb.errors.ChromaError, ValueError, KeyError):
        return False


def rebuild_text_from_chroma(
    doc_hash: str, client: ClientAPI | None = None
) -> str | None:
    """Rebuild full document text from stored Chroma chunks sorted by index."""
    _validate_hash(doc_hash)

    if client is None:
        settings = get_settings()
        client = chromadb.PersistentClient(path=settings.chroma_dir)

    collection_name = get_chroma_collection_name(doc_hash)
    try:
        collection = client.get_collection(name=collection_name)
    except (chromadb.errors.ChromaError, ValueError, KeyError):
        return None

    if collection.count() == 0:
        return None

    stored = collection.get(include=["documents"])
    ids: list[str] = stored.get("ids", [])
    docs: list[str] = stored.get("documents", [])
    if not ids or not docs:
        return None

    def _get_sort_index(item_id: str) -> int:
        parts = item_id.rsplit(":", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return int(parts[1])
        return 0

    pairs = sorted(zip(ids, docs, strict=False), key=lambda p: _get_sort_index(p[0]))
    return "\n\n".join(doc for _, doc in pairs if doc is not None)


STOP_WORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "aren't",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "can't",
    "cannot",
    "could",
    "couldn't",
    "did",
    "didn't",
    "do",
    "does",
    "doesn't",
    "doing",
    "don't",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "hadn't",
    "has",
    "hasn't",
    "have",
    "haven't",
    "having",
    "he",
    "he'd",
    "he'll",
    "he's",
    "her",
    "here",
    "here's",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "how's",
    "i",
    "i'd",
    "i'll",
    "i'm",
    "i've",
    "if",
    "in",
    "into",
    "is",
    "isn't",
    "it",
    "it's",
    "its",
    "itself",
    "let's",
    "me",
    "more",
    "most",
    "mustn't",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "ought",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "shan't",
    "she",
    "she'd",
    "she'll",
    "she's",
    "should",
    "shouldn't",
    "so",
    "some",
    "such",
    "than",
    "that",
    "that's",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "there's",
    "these",
    "they",
    "they'd",
    "they'll",
    "they're",
    "they've",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "wasn't",
    "we",
    "we'd",
    "we'll",
    "we're",
    "we've",
    "were",
    "weren't",
    "what",
    "what's",
    "when",
    "when's",
    "where",
    "where's",
    "which",
    "while",
    "who",
    "who's",
    "whom",
    "why",
    "why's",
    "with",
    "won't",
    "would",
    "wouldn't",
    "you",
    "you'd",
    "you'll",
    "you're",
    "you've",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


def _extract_chunk_sentences(chunk_text: str) -> list[str]:
    """Extract complete sentences as exact substrings of chunk_text."""
    if not chunk_text:
        return []
    pattern = r"(?:^|\s*)([^\s].*?[.!?])(?=\s|$)"
    matches = list(re.finditer(pattern, chunk_text, flags=re.DOTALL))
    if matches:
        return [m.group(1).strip() for m in matches if m.group(1).strip()]
    return [chunk_text.strip()] if chunk_text.strip() else []


def extract_snippet(chunk_text: str, question: str = "", max_chars: int = 200) -> str:
    """Pick the complete sentence sharing the most meaningful words with the question.

    If no sentence shares a word, uses the first complete sentence.
    A snippet is a complete sentence, at most max_chars, and an exact substring without ellipses.
    """
    if not chunk_text:
        return ""

    sentences = _extract_chunk_sentences(chunk_text)
    if not sentences:
        return ""

    q_words = {
        w.lower()
        for w in re.findall(r"\b\w+\b", question)
        if w.lower() not in STOP_WORDS and len(w) > 1
    }

    eligible = [s for s in sentences if len(s) <= max_chars]
    if not eligible:
        first = sentences[0]
        if len(first) <= max_chars:
            return first
        cut = first[:max_chars]
        last_ws = max(cut.rfind(" "), cut.rfind("\n"), cut.rfind("\t"))
        return cut[:last_ws] if last_ws > 0 else cut

    if q_words:
        scored: list[tuple[int, int, str]] = []
        for idx, sent in enumerate(eligible):
            s_words = {
                w.lower()
                for w in re.findall(r"\b\w+\b", sent)
                if w.lower() not in STOP_WORDS
            }
            overlap = len(q_words & s_words)
            scored.append((-overlap, idx, sent))

        scored.sort()
        if scored[0][0] < 0:
            return scored[0][2]

    return eligible[0]


GREETING_OR_SMALLTALK_PATTERNS = [
    # Gratitude
    r"^(thanks?|thank\s+you)(\s+(so\s+much|very\s+much|a\s+lot|again|for\s+your\s+help|for\s+helping|for\s+the\s+help))?$",
    r"^(many\s+thanks|thx|ty|much\s+appreciated|greatly\s+appreciated|appreciate\s+it)$",
    # Greetings
    r"^(hi|hello|hey|howdy|greetings|hola)(\s+(there|assistant|bot|mitra))?$",
    r"^good\s+(morning|afternoon|evening|day)(\s+(there|assistant|bot|mitra))?$",
    # Farewells
    r"^(bye|goodbye|see\s+ya|see\s+you|farewell|cya)$",
    r"^have\s+a\s+(good|nice|great)\s+(day|night|one)$",
    # Small talk queries
    r"^(how\s+are\s+you|who\s+are\s+you|what\s+are\s+you|what\s+can\s+you\s+do|what\s+is\s+your\s+name|tell\s+me\s+about\s+yourself)$",
    r"^(i\s+love\s+you|love\s+you|i\s+like\s+you)$",
    # Acknowledgments
    r"^(ok|okay|cool|great|awesome|got\s+it|understood|nice|perfect|alright|fine|sure)$",
]

REPLY_NO_PASSAGES_PATTERNS = [
    # Fallback / ungrounded replies
    r"does not contain information to answer this question",
    r"the uploaded paper does not contain",
    r"(the\s+)?(paper|text|excerpts?|document)\s+(does|do)\s+not\s+(contain|mention|state|discuss|provide)",
    r"not\s+(found|mentioned|stated|discussed|provided)\s+in\s+the\s+(paper|text|excerpts?|document)",
    r"there\s+is\s+no\s+(mention|information|evidence)\s+(of|about|in)",
    r"i\s+(cannot|can't|am\s+unable\s+to)\s+(find|answer|determine)",
    # Pleasantry replies
    r"^(you('re|\s+are)\s+welcome|happy\s+to\s+help|glad\s+to\s+help|my\s+pleasure|anytime|no\s+problem|don't\s+mention\s+it)\b",
    r"^(hello|hi|hey|greetings)[\s,!.]+(how\s+can\s+i|what\s+can\s+i|how\s+may\s+i|i\s+am|i'm)\b",
    r"^(i\s+am|i'm)\s+an?\s+(ai|research|helpful)\b",
    r"^(good\s+(morning|afternoon|evening|day))\b",
]


def is_greeting_or_smalltalk(text: str) -> bool:
    """Check if text is a greeting, small talk, or conversational pleasantry."""
    if not text:
        return False
    normalized = re.sub(r"[^\w\s]", "", text.strip().lower())
    for pattern in GREETING_OR_SMALLTALK_PATTERNS:
        if re.search(pattern, normalized):
            return True
    return False


def is_unusable_or_negative_reply(answer: str) -> bool:
    """Check if an answer is the fallback sentence, small talk, or indicates excerpts were not used."""
    if not answer or not answer.strip():
        return True
    clean = answer.strip()
    if clean == FALLBACK_GROUNDING_MESSAGE.strip():
        return True
    lower = clean.lower()
    for pattern in REPLY_NO_PASSAGES_PATTERNS:
        if re.search(pattern, lower):
            return True
    return False


def should_send_sources(
    answer: str,
    sources: list[ChatSource],
    question: str = "",
) -> bool:
    """Return True only if the answer is grounded, not small talk/greeting/fallback, and used retrieved passages."""
    if not sources:
        return False
    if is_greeting_or_smalltalk(question):
        return False
    if is_greeting_or_smalltalk(answer):
        return False
    return not is_unusable_or_negative_reply(answer)


def extract_sources(
    chunks: list[RetrievedChunk], question: str = "", max_sources: int = 3
) -> list[ChatSource]:
    """Deduplicate sources by (page_number, snippet) preserving distance order, returning at most max_sources."""
    sorted_chunks = sorted(chunks, key=lambda c: c.distance)
    sources: list[ChatSource] = []
    seen: set[tuple[int | None, str]] = set()
    for chunk in sorted_chunks:
        snippet = extract_snippet(chunk.text, question=question)
        if not snippet:
            continue
        key = (chunk.page, snippet)
        if key not in seen:
            seen.add(key)
            sources.append(ChatSource(page_number=chunk.page, snippet=snippet))
            if len(sources) >= max_sources:
                break
    return sources


def format_metadata_block(metadata: dict[str, Any] | None = None) -> str:
    """Format document metadata into a <DOCUMENT_METADATA> block."""
    meta = metadata or {}
    title = meta.get("title") or "Not specified"
    authors = meta.get("authors") or "Not specified"
    publisher = meta.get("detected_publisher") or "Not specified"
    venue = meta.get("detected_venue") or "Not specified"
    pub_year = meta.get("publication_year") or "Not specified"

    return f"""<DOCUMENT_METADATA>
Title: {title}
Authors: {authors}
Publisher: {publisher}
Venue: {venue}
Publication Year: {pub_year}
</DOCUMENT_METADATA>"""


def format_retrieved_chunks(chunks: list[RetrievedChunk] | None = None) -> str:
    """Format retrieved document chunks into a <RETRIEVED_CHUNKS> block."""
    if not chunks:
        return "<RETRIEVED_CHUNKS>\n(No relevant excerpts found)\n</RETRIEVED_CHUNKS>"
    parts: list[str] = []
    for c in chunks:
        parts.append(f"[Page {c.page}]\n{c.text}")
    return "<RETRIEVED_CHUNKS>\n" + "\n\n".join(parts) + "\n</RETRIEVED_CHUNKS>"


def format_chat_system_prompt(
    metadata: dict[str, Any] | None = None,
    chunks: list[RetrievedChunk] | None = None,
) -> str:
    """Format chat system prompt with unified metadata and retrieved chunks."""
    metadata_block = format_metadata_block(metadata)
    retrieved_chunks = format_retrieved_chunks(chunks)
    return CHAT_SYSTEM_PROMPT_TEMPLATE.format(
        metadata_block=metadata_block,
        retrieved_chunks=retrieved_chunks,
    ).strip()


def assemble_chat_messages(
    question: str,
    history: list[ChatMessage],
    chunks: list[RetrievedChunk] | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Assemble chat messages with unified system instructions, metadata, trimmed history, and user question."""
    chunks_list = chunks if chunks is not None else []
    system_prompt = format_chat_system_prompt(metadata=metadata, chunks=chunks_list)
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]

    # Keep strictly the last 3 turns of history (up to last 6 messages)
    recent_history = history[-6:] if history else []
    for msg in recent_history:
        messages.append({"role": msg.role, "content": msg.content})

    user_content = f"Question: {question}"
    messages.append({"role": "user", "content": user_content})

    return messages


async def stream_chat_response(
    messages: list[dict[str, str]],
    sources: list[ChatSource],
    client: Any,
    question: str = "",
) -> AsyncIterator[str]:
    """Stream chat response tokens, followed by sources and completion signal in SSE format."""
    settings = get_settings()
    try:
        response_stream = await client.chat.completions.create(
            model=settings.model_name,
            messages=messages,
            stream=True,
        )
        full_answer = ""
        async for chunk in response_stream:
            delta = None
            if hasattr(chunk, "choices") and chunk.choices:
                delta_obj = getattr(chunk.choices[0], "delta", None)
                if delta_obj is not None:
                    if isinstance(delta_obj, dict):
                        delta = delta_obj.get("content")
                    else:
                        delta = getattr(delta_obj, "content", None)
            elif isinstance(chunk, dict):
                choices = chunk.get("choices", [])
                if choices:
                    delta_obj = choices[0].get("delta", {})
                    delta = delta_obj.get("content")

            if delta:
                full_answer += delta
                yield f"event: token\ndata: {json.dumps({'text': delta})}\n\n"

        if not should_send_sources(full_answer, sources, question=question):
            sources_payload: list[dict[str, Any]] = []
        else:
            sources_payload = [s.model_dump() for s in sources[:3]]

        yield f"event: sources\ndata: {json.dumps(sources_payload)}\n\n"
        yield f"event: done\ndata: {json.dumps({})}\n\n"
    except openai.AuthenticationError as exc:
        logger.warning(
            "AI provider AuthenticationError during chat streaming: status %s",
            getattr(exc, "status_code", 401),
        )
        yield f"event: error\ndata: {json.dumps({'detail': 'AI provider authentication failed.'})}\n\n"
    except openai.RateLimitError as exc:
        logger.warning(
            "AI provider RateLimitError during chat streaming: status %s",
            getattr(exc, "status_code", 429),
        )
        yield f"event: error\ndata: {json.dumps({'detail': 'AI provider rate limit exceeded.'})}\n\n"
    except (openai.APIConnectionError, openai.APITimeoutError) as exc:
        logger.warning(
            "AI provider connection/timeout error during chat streaming: %s",
            type(exc).__name__,
        )
        yield f"event: error\ndata: {json.dumps({'detail': 'AI provider connection or timeout error.'})}\n\n"
    except openai.APIStatusError as exc:
        logger.warning(
            "AI provider APIStatusError during chat streaming: status %s",
            exc.status_code,
        )
        detail_msg = (
            f"The AI provider returned an error (status {exc.status_code}). "
            "Check MODEL_NAME and EMBEDDING_MODEL in backend/.env."
        )
        yield f"event: error\ndata: {json.dumps({'detail': detail_msg})}\n\n"
    except Exception as exc:
        logger.exception("Error during chat response streaming: %s", type(exc).__name__)
        yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"


async def index_document(
    doc_hash: str,
    chunks: list[dict[str, Any]],
    embed_fn: EmbedFn,
    client: ClientAPI | None = None,
) -> None:
    """Index document chunks into ChromaDB collection.

    Raises:
        ValueError: If doc_hash is invalid or if chunks is empty.
    """
    _validate_hash(doc_hash)
    if not chunks:
        raise ValueError("Document has zero chunks; cannot index.")

    settings = get_settings()
    if client is None:
        client = chromadb.PersistentClient(path=settings.chroma_dir)

    collection_name = get_chroma_collection_name(doc_hash)

    # Check if collection already exists
    existing_collection = None
    try:
        existing_collection = client.get_collection(name=collection_name)
    except (chromadb.errors.ChromaError, ValueError, KeyError):
        existing_collection = None

    if existing_collection is not None:
        coll_meta = existing_collection.metadata or {}
        stored_model = coll_meta.get("embedding_model")
        if stored_model != settings.embedding_model:
            logger.warning(
                "Collection %s index was rebuilt because the embedding model changed (%s -> %s)",
                collection_name,
                stored_model,
                settings.embedding_model,
            )
            client.delete_collection(name=collection_name)
            existing_collection = None
        else:
            current_count = existing_collection.count()
            if current_count == len(chunks):
                logger.info(
                    "Collection %s already indexed with %d chunks; skipping re-indexing",
                    collection_name,
                    current_count,
                )
                return
            else:
                logger.warning(
                    "Collection %s has count mismatch (%d != %d); resetting collection",
                    collection_name,
                    current_count,
                    len(chunks),
                )
                client.delete_collection(name=collection_name)
                existing_collection = None

    logger.info(
        "Embedding and indexing %d chunks for doc_hash %s", len(chunks), doc_hash
    )
    texts = [str(c["text"]) for c in chunks]
    ids = [f"{doc_hash}:{i}" for i in range(len(chunks))]
    metadatas: list[dict[str, Any]] = [{"page": int(c["page"])} for c in chunks]

    embeddings = await embed_fn(texts)
    embedding_dim = len(embeddings[0]) if embeddings else 0

    collection = client.create_collection(
        name=collection_name,
        metadata={
            "hnsw:space": "cosine",
            "embedding_model": settings.embedding_model,
            "embedding_dim": embedding_dim,
        },
    )
    collection.add(
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=embeddings,
    )
    logger.info(
        "Successfully indexed %d chunks in collection %s", len(chunks), collection_name
    )


async def retrieve(
    doc_hash: str,
    query: str,
    embed_fn: EmbedFn,
    top_k: int = 5,
    client: ClientAPI | None = None,
) -> list[RetrievedChunk]:
    """Retrieve top-k relevant chunks for a query from the document's Chroma collection.

    Clamps top_k to stored chunk count. Page provenance comes strictly from metadata.
    """
    _validate_hash(doc_hash)

    if client is None:
        settings = get_settings()
        client = chromadb.PersistentClient(path=settings.chroma_dir)

    collection_name = get_chroma_collection_name(doc_hash)
    try:
        collection = client.get_collection(name=collection_name)
    except (chromadb.errors.ChromaError, ValueError, KeyError) as exc:
        logger.warning("Collection %s not found in Chroma: %s", collection_name, exc)
        return []

    total_count = collection.count()
    if total_count == 0:
        return []

    clamped_k = min(top_k, total_count)
    if clamped_k <= 0:
        return []

    query_embeddings = await embed_fn([query])
    query_dim = len(query_embeddings[0]) if query_embeddings else 0

    coll_meta = collection.metadata or {}
    stored_dim = coll_meta.get("embedding_dim")
    if stored_dim is not None and query_dim != stored_dim:
        raise EmbeddingDimensionMismatchError(
            f"Query embedding dimension ({query_dim}) does not match collection embedding dimension ({stored_dim})."
        )

    query_result = collection.query(
        query_embeddings=query_embeddings,
        n_results=clamped_k,
    )

    retrieved: list[RetrievedChunk] = []
    docs = query_result.get("documents", [[]])[0]
    metas = query_result.get("metadatas", [[]])[0]
    distances = (
        query_result.get("distances", [[]])[0]
        if query_result.get("distances")
        else [0.0] * len(docs)
    )

    for doc_text, meta, dist in zip(docs, metas, distances, strict=False):
        page_num = int(meta.get("page", 1)) if meta else 1
        retrieved.append(
            RetrievedChunk(
                text=str(doc_text),
                page=page_num,
                distance=float(dist),
            )
        )

    return retrieved


CHAT_SYSTEM_PROMPT = CHAT_SYSTEM_PROMPT_TEMPLATE

OVERVIEW_SYSTEM_PROMPT = """You are a helpful research assistant providing an overview of an academic paper.
Provide a clear, well-structured, high-level summary of the paper based strictly on the provided text.
Explain the core problem, methodology, key findings, and conclusions.
Do not use outside knowledge or extrapolate beyond the provided text."""

OUTSIDE_PAPER_REFUSAL = (
    "I can only answer questions about this paper. "
    "Ask me about its problem, methods, or results."
)


def assemble_conversational_messages(
    message: str,
    history: list[ChatMessage],
    metadata: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Assemble conversational chat messages with unified system prompt and last 3 turns of history."""
    return assemble_chat_messages(
        question=message,
        history=history,
        chunks=[],
        metadata=metadata,
    )


def assemble_overview_messages(
    message: str,
    history: list[ChatMessage],
    context_text: str,
) -> list[dict[str, str]]:
    """Assemble overview chat messages with overview system prompt, last 3 turns, and paper text."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": OVERVIEW_SYSTEM_PROMPT}
    ]
    recent_history = history[-6:] if history else []
    for msg in recent_history:
        messages.append({"role": msg.role, "content": msg.content})
    user_content = (
        f"<PAPER_TEXT>\n{context_text.strip()}\n</PAPER_TEXT>\n\nQuestion: {message}"
    )
    messages.append({"role": "user", "content": user_content})
    return messages


async def stream_static_message(text: str) -> AsyncIterator[str]:
    """Stream a static message conforming to the SSE token -> sources -> done protocol."""
    yield f"event: token\ndata: {json.dumps({'text': text})}\n\n"
    yield f"event: sources\ndata: {json.dumps([])}\n\n"
    yield f"event: done\ndata: {json.dumps({})}\n\n"


def get_document_page_count(doc_hash: str, client: ClientAPI | None = None) -> int:
    """Return max page number from Chroma chunks metadata, defaulting to 1."""
    _validate_hash(doc_hash)
    if client is None:
        settings = get_settings()
        client = chromadb.PersistentClient(path=settings.chroma_dir)

    collection_name = get_chroma_collection_name(doc_hash)
    try:
        collection = client.get_collection(name=collection_name)
        stored = collection.get(include=["metadatas"])
        metadatas = stored.get("metadatas", []) or []
        pages = [
            int(m["page"]) for m in metadatas if isinstance(m, dict) and "page" in m
        ]
        return max(pages) if pages else 1
    except (chromadb.errors.ChromaError, ValueError, KeyError):
        return 1


def get_title_authors_abstract(doc_hash: str) -> str:
    """Retrieve pre-indexed title_authors_abstract from summary cache."""
    from app.core.dependencies import get_summary_cache

    cache = get_summary_cache()
    summary_data = cache.get(doc_hash)
    if not summary_data:
        return ""
    if isinstance(summary_data, dict):
        if "header" in summary_data and isinstance(summary_data["header"], dict):
            h = summary_data["header"]
            return f"{h.get('title', '')} by {h.get('authors', '')}\n\n{h.get('abstract', '')}".strip()
        if "title_authors_abstract" in summary_data:
            return str(summary_data["title_authors_abstract"]).strip()
    elif hasattr(summary_data, "header"):
        h = summary_data.header
        return f"{h.title} by {h.authors}\n\n{h.abstract}".strip()
    return str(summary_data).strip()
