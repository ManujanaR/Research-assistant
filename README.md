# Mitra Research Assistant

A full-stack web application designed for researchers and engineers to upload research papers in PDF format, receive a structured 5-section summary, and ask natural-language questions through an interactive, grounded chat interface.

> **Current Project Status**: Under active step-by-step construction. Commits 1a–1c (foundational repository scaffolding) are in place. Application endpoints and frontend UI components are being incrementally implemented according to [SPEC.md](SPEC.md).

## Implementation Status

| Feature / Component | Status | Description |
| :--- | :--- | :--- |
| **Backend Base & Health** | **Completed** | FastAPI server running with `/health` endpoint. |
| **Frontend Base** | **Completed** | Next.js 15.5 & React 19.3 App Router placeholder. |
| **Upload Validation** | *Planned (Commit 3)* | MIME type (415), size limit (413), and SHA-256 on receipt. |
| **PDF Parser** | *Planned (Commit 4)* | PyMuPDF text extraction, 422 empty scan rejection, page chunking. |
| **Summary Cache** | *Planned (Commit 5)* | SHA-256 keyed cache (in-memory with disk fallback). |
| **Structured Summarizer** | *Planned (Commit 6–7)*| 5-section `SummarySchema`, OpenAI structured output, 1-retry rule. |
| **Vector Indexing & RAG** | *Planned (Commit 8)* | ChromaDB vector store in `.chroma/`, `text-embedding-3-small`. |
| **Grounded Chat & Citations** | *Planned (Commit 9)* | Multi-turn sliding history, SSE streaming, page citations. |
| **Frontend UI Components** | *Planned (Commit 10–12)*| `UploadZone`, `SummaryView`, `ChatPanel`, `SourceCard`. |

## Prerequisites

- **Python**: 3.11+
- **Node.js**: 20.9 or later
- **OpenAI API Key**: Required for live manual testing from Commit 6 onward (`OPENAI_API_KEY`). Automated test suites (`pytest`) always run against mocked clients without needing a live key.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI (async), PyMuPDF (`fitz`), ChromaDB, OpenAI SDK (`gpt-4o` and `text-embedding-3-small`), Pydantic v2.
- **Frontend**: Next.js 15.5 (App Router), React 19.3, TypeScript 5.9, Tailwind CSS 3.4, Lucide React 0.475.

## Target Repository Layout

```
/
├── AGENTS.md                  # Development instructions & constraints
├── SPEC.md                    # Detailed application specification
├── README.md                  # Project overview and setup instructions
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entry point & CORS (current: /health route)
│   │   ├── api/               # API route handlers (planned: upload, summary, chat)
│   │   ├── services/          # Business logic (planned: pdf_parser, summarizer, qa, cache)
│   │   ├── schemas/           # Pydantic models (planned: summary, upload, chat)
│   │   └── core/config.py     # Environment configuration (planned: Commit 2)
│   ├── tests/
│   │   ├── test_health.py     # Baseline health endpoint test (completed)
│   │   └── fixtures/          # Test PDF fixtures (planned: Commit 4)
│   ├── requirements.txt       # Python dependencies
│   └── .env.example           # Backend environment template
└── frontend/
    ├── app/
    │   ├── layout.tsx         # Root layout with Tailwind styling (completed)
    │   └── page.tsx           # Placeholder landing page (wired in Commit 12)
    ├── components/            # UI components (planned: UploadZone, SummaryView, ChatPanel, SourceCard)
    ├── lib/api.ts             # Typed backend API client (planned: Commit 10)
    ├── package.json           # Frontend dependencies (Next.js 15.5, React 19.3, lockfile-pinned)
    └── .env.local.example     # Frontend environment template
```

## Quick Start (Development In Progress)

> **Note**: The application is currently under construction. Running the dev servers will display the initial placeholder landing page and verify backend `/health`. Full document processing and chat become interactive at Commit 12.

### 1. Backend Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env and supply your OPENAI_API_KEY (needed from Commit 6 onward)
uvicorn app.main:app --reload --port 8000
```
Backend health check can be verified at: [http://localhost:8000/health](http://localhost:8000/health)

### 2. Frontend Setup

```bash
cd frontend
npm ci
cp .env.local.example .env.local
npm run dev
```

The placeholder interface is accessible at [http://localhost:3000](http://localhost:3000).

## Testing & Quality Assurance

- **Backend Tests & Linting**:
  ```bash
  cd backend
  pytest                 # Currently runs test_health.py (more tests added per commit)
  ruff check .
  ruff format --check .
  ```
- **Frontend Type Check, Linting & Build**:
  ```bash
  cd frontend
  npm run lint
  npx tsc --noEmit
  npm run build          # Verifies production Next.js compilation
  ```
