# Mitra Research Assistant

A full-stack web application designed for researchers and engineers to upload research papers in PDF format, receive a structured 5-section summary, and ask natural-language questions through an interactive, grounded chat interface.

## Core Features

1. **Single PDF Upload**: Strict validation for MIME type (`application/pdf`), maximum file size (`MAX_UPLOAD_MB`), and detection of unscannable/empty-text documents.
2. **Structured Summary Generation**: Pre-defined 5-section template (Title & Authors & Abstract, Problem Statement, Methodology, Key Results, Conclusion), cached by SHA-256 hash to eliminate redundant LLM calls.
3. **Grounded Question-Answering Chat**: Retrieval-Augmented Generation (RAG) powered by ChromaDB, streaming responses via Server-Sent Events (SSE) with verifiable page citations.

## Tech Stack

- **Backend**: Python 3.11+, FastAPI (async), PyMuPDF (`fitz`), ChromaDB, OpenAI SDK (`gpt-4o` and `text-embedding-3-small`), Pydantic v2.
- **Frontend**: Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS, Lucide React.

## Repository Layout

```
/
├── AGENTS.md                  # Development instructions & constraints
├── SPEC.md                    # Detailed application specification
├── README.md                  # Project overview and setup instructions
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI entry point, CORS, and routers
│   │   ├── api/               # API route handlers (upload, summary, chat)
│   │   ├── services/          # Business logic (pdf_parser, summarizer, qa, cache)
│   │   ├── schemas/           # Pydantic models (SummarySchema, ChatRequest, etc.)
│   │   └── core/config.py     # Environment configuration
│   ├── tests/                 # Automated test suite (mocked LLM)
│   ├── requirements.txt       # Python dependencies
│   └── .env.example           # Backend environment template
└── frontend/
    ├── app/                   # Next.js app router pages
    ├── components/            # UI components (UploadZone, SummaryView, ChatPanel, SourceCard)
    ├── lib/api.ts             # Typed backend API client
    ├── package.json           # Frontend dependencies
    └── .env.local.example     # Frontend environment template
```

## Quick Start (Local Development)

### 1. Backend Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# Edit .env and supply your OPENAI_API_KEY
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Visit [http://localhost:3000](http://localhost:3000) in your browser.

## Testing & Quality Assurance

- **Backend Tests & Linting**:
  ```bash
  cd backend
  pytest
  ruff check .
  ruff format --check .
  ```
- **Frontend Type Check & Linting**:
  ```bash
  cd frontend
  npm run lint
  npx tsc --noEmit
  npm run build
  ```
