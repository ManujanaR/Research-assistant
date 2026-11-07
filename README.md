# Mitra Research Assistant

A full-stack web application designed for researchers and engineers to upload research papers in PDF format, receive a structured 5-section summary, and ask natural-language questions through an interactive, grounded chat interface with page citations.

## Implementation Status

| Feature / Component | Status | Description |
| :--- | :--- | :--- |
| **Backend Base & Health** | **Completed** | FastAPI server running with `/health` endpoint and CORS middleware. |
| **Frontend Base & Layout** | **Completed** | Next.js 15.5 & React 19.3 App Router shell with responsive layout. |
| **Upload Validation** | **Completed** | Multipart upload validation with MIME check (415), size limit (413), and SHA-256 calculation on receipt. |
| **PDF Parser** | **Completed** | PyMuPDF text extraction, image-only/scanned PDF rejection (422), and page chunking. |
| **Summary Cache** | **Completed** | SHA-256 keyed cache with memory store and atomic disk fallback in `.cache/summaries/`. |
| **Structured Summarizer** | **Completed** | 5-section `SummarySchema` (`title_authors_abstract`, `problem_statement`, `methodology`, `key_results`, `conclusion`), strict JSON structured output, 1-retry validation rule, and prompt injection defense. |
| **Vector Indexing & RAG** | **Completed** | ChromaDB persistent store in `.chroma/`, `text-embedding-3-small` embeddings, and top-k cosine similarity retrieval. |
| **Grounded Chat & Citations** | **Completed** | Grounded Q&A chat with 5-turn sliding history (10 messages), SSE token streaming, exact source snippets ($\le 200$ chars), and page provenance citations. |
| **Frontend UI Components** | **Completed** | `UploadZone`, `SummaryView`, `ChatPanel`, and `SourceCard` with loading, empty, and error states. |
| **End-to-End Page Integration** | **Completed** | Complete UI flow in `app/page.tsx`, automated full-flow smoke test (`test_e2e_smoke.py`), and paper reset functionality. |

## Prerequisites

- **Python**: 3.11+ (Python 3.14 tested)
- **Node.js**: 20.9 or later
- **OpenAI API Key**: Required for live summarization and chat (`OPENAI_API_KEY`). All test suites use mocked clients and run without making real API calls.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI (async), PyMuPDF (`pymupdf`), ChromaDB, OpenAI Python SDK (`gpt-4o` and `text-embedding-3-small`), Pydantic v2.
- **Frontend**: Next.js 15.5 (App Router), React 19.3, TypeScript 5.7+, Tailwind CSS 3.4, Lucide React, Vitest 5.1, Testing Library.

## Repository Layout

```
/
├── AGENTS.md                  # Development instructions & constraints
├── SPEC.md                    # Detailed application specification
├── README.md                  # Project overview and setup instructions
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entry point & CORS
│   │   ├── api/               # API route handlers: upload, summary, chat
│   │   ├── services/          # pdf_parser, summarizer, qa, cache, summary_service
│   │   ├── schemas/           # Pydantic models: upload, summary, chat
│   │   └── core/              # config.py, dependencies.py
│   ├── tests/
│   │   ├── fixtures/          # Test PDF fixtures (sample_scanned.pdf)
│   │   ├── test_upload_validation.py
│   │   ├── test_pdf_parser.py
│   │   ├── test_cache.py
│   │   ├── test_summarizer.py
│   │   ├── test_summary_endpoint.py
│   │   ├── test_retrieval.py
│   │   ├── test_chat_endpoint.py
│   │   ├── test_text_rehydration.py
│   │   └── test_e2e_smoke.py  # End-to-end integration smoke test
│   ├── scripts/
│   │   └── generate_scanned_pdf.py
│   ├── requirements.txt       # Python dependencies
│   └── .env.example           # Backend environment template
└── frontend/
    ├── app/
    │   ├── layout.tsx         # Responsive application shell
    │   ├── page.tsx           # Main page wiring upload, summary, and chat
    │   └── globals.css
    ├── components/            # UploadZone, SummaryView, ChatPanel, SourceCard
    ├── lib/
    │   ├── api.ts             # Typed backend API client & models
    │   └── sse.ts             # Server-Sent Events parser
    ├── package.json           # Frontend dependencies and test script
    ├── vitest.config.mts      # Vitest configuration with jsdom & React plugin
    └── .env.local.example     # Frontend environment template
```

## Quick Start

### 1. Backend Setup

From the repository root:

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env and supply your API key and provider configuration
uvicorn app.main:app --reload --port 8000
```

Verify backend health at [http://localhost:8000/health](http://localhost:8000/health) (`{"status":"ok"}`).

### Environment Variables

Configure backend settings in `backend/.env`:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `LLM_PROVIDER` | `openai` | LLM provider backend (`openai`). |
| `OPENAI_API_KEY` | `""` | API key for OpenAI or OpenAI-compatible provider. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Base URL for the OpenAI-compatible API endpoint. |
| `MODEL_NAME` | `gpt-4o` | Chat & summarization model name. |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Vector embedding model name. |
| `MAX_UPLOAD_MB` | `20` | Maximum allowed PDF file size in megabytes. |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins. |
| `SUMMARY_CACHE_DIR` | `.cache/summaries` | Directory for disk-persisted summaries. |
| `CHROMA_DIR` | `.chroma` | Directory for persistent ChromaDB storage. |
| `CITATION_MAX_DISTANCE` | `0.6` | Maximum retrieval distance for citation relevance. |

#### Provider Configuration Examples

##### Direct OpenAI (Default)

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4o
EMBEDDING_MODEL=text-embedding-3-small
```


#### Citation Threshold Calibration

`CITATION_MAX_DISTANCE` is calibrated per embedding model. After changing `EMBEDDING_MODEL`, run `scripts/calibrate_citation_threshold.py` and update the threshold.

### 2. Frontend Setup

In a separate terminal from the repository root:

```bash
cd frontend
npm ci
cp .env.local.example .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Persistence & Restart Behavior

The application is designed to withstand server restarts without loss of document state:

1. **Summary Persistence**: Summaries are cached atomically on disk under `.cache/summaries/{doc_hash}.json`. A subsequent request for an existing document hash is served immediately from disk cache without invoking the LLM.
2. **Vector Index Persistence**: Chunks and their embeddings are persisted in ChromaDB under `.chroma/` in collections named `doc_{first_32_chars_of_hash}`. Re-indexing the same document is skipped automatically.
3. **Paper Text Rehydration**: In-memory paper text is backed by the ChromaDB vector index. If the backend restarts and receives a summary request with a summary cache miss, it rehydrates the full paper text by fetching stored chunks from ChromaDB, sorting them by their original numeric index (`{doc_hash}:{index}`), and caching them in memory.
4. **Temporary File Isolation**: Raw uploaded PDF files are stored in temporary files only during parsing and indexing, and are cleaned up in a `finally` block immediately after processing.

## Testing & Quality Assurance

### Backend Verification

Run from `backend/`:

```bash
cd backend
pytest -v              # Runs 71 unit and integration tests + 2 placeholder fixtures
ruff check .           # Lints all Python code
ruff format --check .  # Verifies PEP 8 formatting
```

### Frontend Verification

Run from `frontend/`:

```bash
cd frontend
npm test               # Runs 30 unit & component tests in Vitest
npm run lint           # ESLint verification
npx tsc --noEmit       # Strict TypeScript type check
npm run build          # Production Next.js compilation
```

## Known Limitations

- **Citation Relevance Filtering**: The `CITATION_MAX_DISTANCE` threshold hides citation cards when the retrieval cosine distance is high (e.g. for completely off-topic questions). However, if the model responds conversationally to an off-topic query, and that query happens to retrieve a chunk with cosine distance below 0.6, citations will still appear alongside the reply. A more restrictive fix (such as enforcing a constrained output format or secondary grounding verification) will be evaluated in future iterations.
