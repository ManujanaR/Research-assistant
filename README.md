# Research Assistant

A full-stack, production-ready research assistant application designed for researchers, scientists, and engineers. Upload academic papers in PDF format, receive an instant, structured 5-section summary, evaluate academic credibility metrics, inspect documents via an integrated PDF viewer, export executive reports to Microsoft Word (`.docx`), and converse through an interactive natural-language chat interface grounded in the paper's contents with page-level citations and multi-section dual-pass retrieval.

[![Specification](https://img.shields.io/badge/Docs-Specification-blue)](docs/spec.md)
[![Architecture Design](https://img.shields.io/badge/Docs-Architecture%20Design-green)](docs/design.md)
[![Multi-Section Retrieval Spec](https://img.shields.io/badge/Docs-Multi--Section%20Retrieval%20Spec-purple)](docs/specs/multi_section_retrieval.md)

> 📖 **Comprehensive Documentation**:
> - [**System Specification & Acceptance Criteria**](docs/spec.md): Complete functional specifications, API contracts, RAG grounding constraints, authentication rules, and acceptance criteria.
> - [**Architecture & UI Design Guide**](docs/design.md): Consolidated design system, component hierarchy, KaTeX math notation architecture, security boundaries, universal multilingual policy, and AWS/Docker deployment topologies.
> - [**Multi-Section Retrieval Specification**](docs/specs/multi_section_retrieval.md): Specification for cross-section comparative inquiry, structured classification flags, and dual-pass retrieval pipelines.

---

## Key Features

- **Single PDF Upload & Ingestion**:
  - Strict validation of `application/pdf` MIME type and 20MB default size limit (`MAX_UPLOAD_MB`).
  - SHA-256 content deduplication preventing redundant processing.
  - Automatic Tesseract OCR fallback for scanned or image-only PDFs with configurable timeouts (`OCR_ENABLED`, `OCR_TIMEOUT_SECONDS`).
  - Centered, accessible drag-and-drop upload zone on both desktop and mobile viewports.
- **Structured 5-Section Summary**:
  - Generated with strict Pydantic schema validation (`SummarySchema`):
    1. *Title, Authors & Abstract*
    2. *Problem Statement*
    3. *Methodology*
    4. *Key Results*
    5. *Conclusion*  
  - Automatic 1-retry schema repair on malformed LLM outputs.
  - Persistent disk caching keyed by document SHA-256.
- **Cross-Section Comparison & Dual-Pass Retrieval**:
  - **Structured Comparative Classification**: The classifier extracts `is_comparative: bool` and `comparison_targets: list[str]` alongside intent and rewritten queries.
  - **Dual-Pass Retrieval Pipeline**: When a comparative question arises (e.g., comparing Abstract claims against Results), the retrieval pipeline runs two targeted passes:
    - *Pass 1 (Abstract Pass)*: Queries the Abstract using structural section queries (`top_k=3`).
    - *Pass 2 (Results/Secondary Pass)*: Queries the Results or Discussion section (`top_k=3`).
  - **Deduplication & Distance Ordering**: Merges passages, eliminates duplicate chunk IDs, and sorts strictly by cosine distance.
  - **Missing Section Fallback**: If a targeted section is absent, reports that the section was not found without substituting arbitrary text.
- **Interactive Persona Suggestion Chips**:
  - Dynamically offered conversational prompt suggestions tailored to user workflows:
    - **Reader Mode**: *"Core Findings"*, *"Methodology"*, *"Dataset / Setup"*.
    - **Author Mode**: *"Flaws & Limitations"*, *"Gaps & Improvements"*, *"Abstract vs Findings"*.
  - Full keyboard accessibility with ARIA tablist patterns (`role="tablist"` / `role="tab"`).
- **Executive Word Export (`.docx`)**:
  - Fast, server-side document generation powered by `python-docx` (`/api/export`).
  - Exports a styled Word report featuring the paper title, authors, venue metadata, full 5-section executive breakdown, and optional Q&A conversation transcripts.
- **Academic Credibility Scoring**:
  - Real-time bibliometric verification via the OpenAlex API (`/api/credibility`).
  - Computes h-index, citation count, publication year, Open Access status, and venue host metrics.
  - **Strict Privacy Boundary**: Only queries by extracted paper title or DOI string. Document bodies, chunks, chat logs, and user identities are never transmitted externally.
- **Built-in PDF Viewer Drawer**:
  - Responsive client-side drawer allowing side-by-side reading of the original PDF alongside summary cards and chat.
  - Strict blob object URL lifecycle management ensuring zero memory leaks.
- **KaTeX Mathematical Notation Rendering**:
  - Native rendering for inline `\(...\)` (or `$ ... $`) and display block `\[...\]` (or `$$ ... $$`) LaTeX equations.
  - Rendered across both structured summary cards and conversational chat message bubbles.
  - Code-block isolation prevents syntax inside backticks (`` ` `` / ```` ``` ````) from accidental LaTeX parsing.
  - Horizontal scrolling enabled on block formulas (`.katex-display`) to preserve responsive layouts.
- **Strict Content Security & HTML Sanitization**:
  - Model and PDF outputs are treated strictly as untrusted text.
  - Markdown renderer operates without `rehype-raw`, completely eliminating stored XSS vectors. Raw HTML tags (e.g., `<script>`, `<img onerror=...>`) render as safe, escaped literal text entities.
- **Universal Multilingual Q&A Policy**:
  - **Native Script Enforcement**: Answers in the user's language using its official native script (e.g., Sinhala Unicode script `සිංහල අකුරු` for Sinhala and Singlish queries).
  - **Phonetic Slang Suppression**: Refuses romanised phonetic slang, translating colloquial intent into grammatically correct native script.
  - **Technical Term Preservation**: Specialized academic terminology, variables, and named entities (e.g., *Transformer architecture*, *BLEU score*) survive in standard English form.
  - **Immutable English Fallback Contract**: Ungrounded queries strictly return the English fallback string (`"The uploaded paper does not contain information to answer this question."`) across all languages, ensuring reliable automated citation suppression.
- **Natural-Language RAG Chat & Intent Classification**:
  - **Structured Classification**: Fast semantic routing (`classifier.py`) distinguishing greetings, general document overviews, specific document questions, comparative questions, and out-of-scope inquiries.
  - **Context-Aware Query Rewriting**: Resolves pronouns (*"it"*, *"the first one"*, *"they"*) and casual phrasing into standalone academic queries using conversation history.
  - **Accurate Provenance Citations**: Returns at most 3 top-ranked sources based on cosine distance. Shows page numbers directly from stored PDF metadata with complete-sentence verbatim snippets ($\le 200$ chars).
  - **Collapsed Citations UI**: Answers display a clean, collapsed `"Sources (N)"` dropdown that expands without cluttering the answer text.
  - **Strict Grounding & Fallback**: Answers are grounded strictly in paper excerpts. Cleanly suppresses citations for small talk, greetings, and ungrounded replies.
- **Authentication & User Data Isolation**:
  - Secure email/password authentication using bcrypt password hashing.
  - JWT session tokens stored in secure, `HttpOnly`, `SameSite=Lax` cookies.
  - SQLite database (`app.db`) isolating uploaded documents, summaries, and chat sessions to the authenticated owner.
- **Crash & Restart Resilience**:
  - Summaries are persisted in `.cache/summaries/{doc_hash}.json`.
  - Vectors and chunks are stored permanently in ChromaDB collections (`.chroma/doc_{doc_hash[:32]}`).
  - Full paper text can be rehydrated from ChromaDB chunks if the backend restarts.

---

## Architecture & Workflows

### System Architecture

```mermaid
flowchart TD
    subgraph Frontend["Frontend (Next.js 15 / TypeScript / Tailwind)"]
        UI_Upload["UploadZone (Drag & Drop PDF)"]
        UI_Summary["SummaryView (5 Structured Sections)"]
        UI_Chat["ChatPanel (SSE Stream & Suggestion Chips)"]
        UI_Drawer["PdfViewerDrawer (Side-by-Side Reading)"]
        UI_Cred["CredibilityCard (Bibliometrics)"]
        UI_Export["ExportButton (DOCX Download)"]
    end

    subgraph Backend["FastAPI Backend (Async Python)"]
        API_Auth["/api/auth (JWT in HttpOnly Cookie)"]
        API_Upload["/api/upload (PyMuPDF & Ingestion)"]
        API_Summary["/api/summary (Cached Structured Output)"]
        API_Chat["/api/chat (Classifier & RAG Stream)"]
        API_Export["/api/export (Word Report Generator)"]
        API_Cred["/api/credibility (OpenAlex Metrics)"]
        
        Service_Parser["pdf_parser.py (PyMuPDF / OCR)"]
        Service_Classifier["classifier.py (Intent & Dual-Pass Targets)"]
        Service_QA["qa.py (Dual-Pass & Single Retrieval)"]
        Service_Export["export_service.py (python-docx)"]
        Service_Cred["credibility_service.py (OpenAlex API)"]
    end

    subgraph Storage["Persistence & AI Services"]
        DB_SQL["SQLite (app.db: Users & Ownership)"]
        Chroma["ChromaDB (.chroma: Embeddings & Chunks)"]
        DiskCache["Disk Cache (.cache: Summaries & Credibility)"]
        OpenAI["OpenAI API (GPT-4o, gpt-4o-mini, text-embedding-3-small)"]
        OpenAlex["OpenAlex API (api.openalex.org: Title/DOI only)"]
    end

    UI_Upload --> API_Upload
    UI_Summary --> API_Summary
    UI_Chat --> API_Chat
    UI_Export --> API_Export
    UI_Cred --> API_Cred
    UI_Drawer -.-> UI_Upload

    API_Upload --> DB_SQL
    API_Upload --> Service_Parser
    API_Upload --> Chroma
    API_Upload --> OpenAI

    API_Summary --> DiskCache
    API_Summary --> OpenAI

    API_Chat --> DB_SQL
    API_Chat --> Service_Classifier
    Service_Classifier --> OpenAI
    API_Chat --> Service_QA
    Service_QA --> Chroma
    Service_QA --> OpenAI

    API_Export --> Service_Export
    API_Export --> DB_SQL

    API_Cred --> Service_Cred
    Service_Cred --> DiskCache
    Service_Cred --> OpenAlex
```

### RAG Chat & Dual-Pass Retrieval Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as User (Browser)
    participant ChatAPI as FastAPI /api/chat
    participant DB as SQLite DB
    participant Classifier as classifier.py (gpt-4o-mini)
    participant Chroma as ChromaDB Vector Store
    participant QA as qa.py & LLM (GPT-4o)

    User->>ChatAPI: POST /api/chat {doc_hash, message, history}
    ChatAPI->>DB: Check ownership (Is doc_hash owned by user?)
    alt Not Owner
        ChatAPI-->>User: 404 Not Found
    end

    ChatAPI->>Classifier: classify_and_rewrite(message, history[-6:])
    Classifier-->>ChatAPI: {intent, query, is_comparative, comparison_targets}

    alt Intent is "chat", "document_overview", or "outside_paper"
        ChatAPI->>QA: Stream response directly without vector search
        QA-->>User: SSE Token stream (sources: [])
    else Intent is "document_question"
        alt is_comparative == true (Cross-Section Comparison)
            ChatAPI->>Chroma: Pass 1: retrieve(doc_hash, query=target_1_query, top_k=3)
            ChatAPI->>Chroma: Pass 2: retrieve(doc_hash, query=target_2_query, top_k=3)
            Note over ChatAPI: Merge passes, deduplicate chunk IDs, sort by cosine distance
        else is_comparative == false (Standard In-Context Retrieval)
            ChatAPI->>Chroma: Single pass: retrieve(doc_hash, query=rewritten_query, top_k=5)
        end

        Note over ChatAPI: Filter distance <= CITATION_MAX_DISTANCE<br/>Sort by distance and take top relevant passages

        ChatAPI->>QA: assemble_chat_messages(question, history[-6:], retrieved_chunks, metadata)
        QA->>QA: Stream tokens via Server-Sent Events (SSE)
        QA-->>User: event: token {"text": "..."}
        QA-->>User: event: sources [{"page_number": 2, "snippet": "..."}]
        QA-->>User: event: done {}
    end
```

---

## Tech Stack

- **Backend**:
  - Python 3.11+ (asyncio, FastAPI)
  - PyMuPDF (`fitz`) & Tesseract OCR (`pytesseract`) for PDF text parsing
  - ChromaDB for persistent vector storage and cosine similarity search
  - OpenAI Python SDK (`gpt-4o`, `gpt-4o-mini`, `text-embedding-3-small`)
  - `python-docx` for structured Word report generation
  - `httpx` for async OpenAlex API client integration
  - SQLAlchemy & SQLite for relational user management and document ownership
  - Pydantic v2 & Pydantic Settings
- **Frontend**:
  - Next.js 15 (App Router)
  - React 19 & TypeScript 5.7+
  - Tailwind CSS 3.4 & Lucide Icons
  - KaTeX for LaTeX mathematical typesetting
  - Vitest & React Testing Library

---

## Repository Layout

```
/
├── AGENTS.md                  # Development instructions & constraints
├── README.md                  # Project documentation
├── docs/
│   ├── spec.md                # Detailed application specification
│   ├── design.md              # Architectural & UI design decisions
│   └── specs/
│       └── multi_section_retrieval.md  # Multi-section dual-pass retrieval spec
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entry point & CORS configuration
│   │   ├── api/               # API routes: auth, upload, summary, chat, export, credibility, health
│   │   ├── services/          # pdf_parser, classifier, qa, summarizer, export_service, credibility_service, etc.
│   │   ├── schemas/           # Pydantic models: auth, upload, summary, chat, export, credibility
│   │   ├── models/            # SQLAlchemy models: user, document_ownership
│   │   ├── db/                # Database engine & session management
│   │   └── core/              # config.py, dependencies.py
│   ├── tests/                 # 227+ automated unit, integration, and smoke tests (28 test suites)
│   │   ├── test_auth_session.py
│   │   ├── test_auth_signup_signin.py
│   │   ├── test_cache.py
│   │   ├── test_calibrate_script.py
│   │   ├── test_chat_endpoint.py
│   │   ├── test_classifier.py
│   │   ├── test_config.py
│   │   ├── test_credibility.py
│   │   ├── test_duplicate_upload.py
│   │   ├── test_e2e_auth.py
│   │   ├── test_e2e_smoke.py
│   │   ├── test_export.py
│   │   ├── test_header_extraction.py
│   │   ├── test_health.py
│   │   ├── test_metadata_chat_grounding.py
│   │   ├── test_multi_section_retrieval.py
│   │   ├── test_natural_chat.py
│   │   ├── test_ocr.py
│   │   ├── test_ownership.py
│   │   ├── test_pdf_parser.py
│   │   ├── test_profile.py
│   │   ├── test_provider_config.py
│   │   ├── test_provider_errors.py
│   │   ├── test_retrieval.py
│   │   ├── test_summarizer.py
│   │   ├── test_summary_endpoint.py
│   │   ├── test_text_rehydration.py
│   │   └── test_upload_validation.py
│   ├── scripts/
│   │   ├── calibrate_citation_threshold.py
│   │   └── generate_scanned_pdf.py
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── app/
    │   ├── layout.tsx         # Root layout with auth provider & responsive shell
    │   ├── page.tsx           # Main workspace (Upload, Summary, Chat, Panels)
    │   ├── signin/page.tsx    # Sign-in page
    │   ├── signup/page.tsx    # Sign-up page
    │   └── globals.css
    ├── components/            # UploadZone, SummaryView, ChatPanel, PdfViewerDrawer, CredibilityCard, ExportButton, etc.
    ├── lib/
    │   ├── api.ts             # Typed API client
    │   └── sse.ts             # SSE parser
    ├── package.json
    ├── vitest.config.mts
    └── .env.local.example
```

---

## Getting Started

### 1. Prerequisites

- **Python**: 3.11 or later
- **Node.js**: 20.9 or later
- **Tesseract OCR**: Required on the host system to process scanned or image-only PDFs (`tesseract-ocr` on Ubuntu/Debian, `tesseract` on Fedora/macOS).
- **OpenAI API Key**: Required for live summarization, query classification, and chat answering. (All test suites run completely offline with mocked providers.)

---

### 2. Backend Setup

From the repository root:

```bash
cd backend

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and supply your OPENAI_API_KEY and AUTH_SECRET_KEY

# Start backend dev server
uvicorn app.main:app --reload --port 8000
```

Verify backend health at [http://localhost:8000/health](http://localhost:8000/health) (`{"status":"ok"}`).

---

### 3. Frontend Setup

In a separate terminal from the repository root:

```bash
cd frontend

# Install dependencies
npm ci

# Configure environment variables
cp .env.local.example .env.local

# Start frontend dev server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `LLM_PROVIDER` | `openai` | LLM provider backend (`openai`). |
| `OPENAI_API_KEY` | `""` | API key for OpenAI or OpenAI-compatible provider. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL for OpenAI-compatible endpoint. |
| `MODEL_NAME` | `gpt-4o` | Chat & summarization model name. |
| `REWRITE_MODEL` | `gpt-4o-mini` | Model used for intent classification and conversational query rewriting. |
| `REWRITE_HISTORY_TURNS` | `3` | Conversation history turns sent to classifier. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Vector embedding model name. |
| `MAX_UPLOAD_MB` | `20` | Maximum allowed PDF file size in MB. |
| `CITATION_MAX_DISTANCE` | `0.6` | Cosine distance cutoff threshold for citation retrieval. |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins. |
| `SUMMARY_CACHE_DIR` | `.cache/summaries` | Directory for disk-persisted summaries. |
| `CREDIBILITY_CACHE_DIR` | `.cache/credibility` | Directory for disk-persisted bibliometric cache. |
| `SEMANTIC_SCHOLAR_API_KEY` | `""` | Optional API key for bibliometric providers. |
| `CHROMA_DIR` | `.chroma` | Directory for persistent ChromaDB storage. |
| `OCR_ENABLED` | `true` | Whether Tesseract OCR is enabled for scanned documents. |
| `OCR_TIMEOUT_SECONDS` | `120` | Maximum seconds allocated for OCR processing. |
| `ENVIRONMENT` | `development` | Runtime environment (`development` or `production`). |
| `AUTH_SECRET_KEY` | `""` | Secret key for signing JWT tokens. Required in production. |
| `AUTH_TOKEN_TTL_MINUTES` | `60` | Session token time-to-live in minutes. |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLAlchemy database URL for users and ownership. |

To generate a secure random string for `AUTH_SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

### Frontend (`frontend/.env.local`)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Backend API URL reachable by the browser. |

---

## Testing & Quality Assurance

Both the backend and frontend include comprehensive automated test suites that run without requiring live network access or paid API keys.

### Backend Verification

Run from `backend/`:

```bash
cd backend

# Run full test suite (227+ passed tests across 28 unit, integration, and smoke test suites)
pytest -v

# Run linting
ruff check .

# Run format check
ruff format --check .
```

### Frontend Verification

Run from `frontend/`:

```bash
cd frontend

# Run unit and component tests (118 passed tests across Markdown, KaTeX, Auth, and UI suites)
npm test

# Linting
npm run lint

# Strict TypeScript type check
npx tsc --noEmit

# Production build test
npm run build
```

---

## Citation Threshold Calibration

`CITATION_MAX_DISTANCE` controls the cosine distance cutoff for retrieval. If you change `EMBEDDING_MODEL` or tune sensitivity, run the built-in calibration script:

```bash
cd backend
python scripts/calibrate_citation_threshold.py \
  --doc-hash <DOC_HASH> \
  --on-topic "What were the key results?" "What was the sample size?" \
  --off-topic "What is the capital of France?" "How to bake a cake?"
```

The script reports group distances and suggests an optimal cutoff threshold.

---

## Known Considerations

- **Single-Server SQLite**: User records and document ownership are stored in local SQLite (`data/app.db`), optimized for single-instance deployments.
- **In-Memory Rate Limiting**: The authentication failure rate limiter maintains state in memory and resets upon server restart.
- **Scanned PDFs & OCR**: Scanned PDFs are processed with OCR. Accuracy depends on scan quality. OCR processing is slower than native text extraction.
