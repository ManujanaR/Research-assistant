# AGENTS.md

Instructions for AI coding agents working in this repository. Read this fully before making changes.

## Project overview

Research Assistant: a full-stack web app where a user uploads one research paper (PDF), receives a structured summary, and asks natural-language questions about it through a chat interface (RAG or full-context Q&A). Due November 10, 2026.

Core requirements, in priority order:
1. Single PDF upload per session.
2. Structured summary with five sections: Title & Authors & Abstract, Problem Statement, Methodology, Key Results, Conclusion. Rendered readably in the UI.
3. Question-answering chat over the uploaded paper, with answers grounded in the paper.

Extras are welcome but must not compromise the core. Do not start extras until the core works end to end.

## Tech stack

- Frontend: Next.js (React) with TypeScript and Tailwind CSS.
- Backend: FastAPI (Python 3.11+), fully async for file handling and LLM streaming.
- PDF parsing: PyMuPDF (`fitz`). Do not switch to Marker unless extraction quality is demonstrably poor on test papers.
- LLM provider: OpenAI (GPT-4o) or Anthropic (Claude Sonnet). Read the key from environment variables only.
- Structured output: Pydantic models for the summary schema.
- Retrieval: ChromaDB for vector storage if RAG is used. Full-context mode (whole paper text in the prompt) is an acceptable alternative for papers under roughly 30 pages.
- Orchestration (optional): LangChain or LlamaIndex. Prefer plain code if it stays simple.

## Repository layout

```
/
├── AGENTS.md
├── README.md
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, router registration, CORS
│   │   ├── api/               # Route modules: upload, summary, chat
│   │   ├── services/          # pdf_parser.py, summarizer.py, qa.py, cache.py
│   │   ├── schemas/           # Pydantic models (SummarySchema, ChatRequest, etc.)
│   │   └── core/config.py     # Settings loaded from env
│   ├── tests/
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── app/                   # Next.js app router pages
    ├── components/            # UploadZone, SummaryView, ChatPanel, SourceCard
    ├── lib/api.ts             # Typed API client for the backend
    ├── package.json
    └── .env.local.example
```

Keep this layout unless there is a clear reason to change it. If you change it, update this file in the same commit.

## Commands

Backend (run from `backend/`):
- Install: `pip install -r requirements.txt`
- Dev server: `uvicorn app.main:app --reload --port 8000`
- Tests: `pytest`
- Lint and format: `ruff check . && ruff format .`

Frontend (run from `frontend/`):
- Install: `npm install`
- Dev server: `npm run dev`
- Build: `npm run build`
- Lint: `npm run lint`
- Type check: `npx tsc --noEmit`

Run the type check, lint, and relevant tests before reporting a task as done.

## Environment variables

Never hardcode secrets. Keys live in `.env` files that are git-ignored.

Backend (`backend/.env`):
- `LLM_PROVIDER` (`openai` or `anthropic`)
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`
- `MODEL_NAME` (for example `gpt-4o` or `claude-sonnet-4-5`)
- `MAX_UPLOAD_MB` (default 20)
- `CORS_ORIGINS` (default `http://localhost:3000`)
- `AUTH_SECRET_KEY` (required in production)
- `AUTH_TOKEN_TTL_MINUTES` (default 60)
- `DATABASE_URL` (default `sqlite:///./data/app.db`)

Frontend (`frontend/.env.local`):
- `NEXT_PUBLIC_API_BASE_URL` (default `http://localhost:8000`)

Update `.env.example` files whenever you add a variable.

## Coding conventions

Python:
- Type hints on all function signatures. Use `async def` for route handlers and any I/O.
- Keep route handlers thin. Put logic in `services/`.
- Validate all request and response bodies with Pydantic.
- Raise `HTTPException` with clear messages for client errors (wrong file type, oversized file, unparseable PDF).
- Log with the standard `logging` module, never `print`.

TypeScript and React:
- Functional components and hooks only.
- Strict TypeScript. Avoid `any`; define types for every API response in `lib/api.ts`.
- Tailwind for styling. Do not add a second CSS framework.
- Handle loading, empty, and error states in every async UI component.

General:
- Small, focused commits with descriptive messages.
- Do not add dependencies without a clear need. Note any new dependency in the summary of your change.
- Do not leave commented-out code, debug prints, or TODOs without an owner or a concrete next step.

## Behavior requirements

Upload:
- Accept only `application/pdf`. Reject other types with a 415 or 400 response.
- Reject files larger than `MAX_UPLOAD_MB`.
- Reject PDFs that yield no extractable text (likely scanned), and say so in the error message.

Summary:
- Generate the summary once per upload and cache it by a SHA-256 hash of the file contents.
- Return the summary as JSON matching the Pydantic schema. If the LLM output fails validation, retry once, then return a clear error.
- The five sections must always be present in the response, even if a section is "Not stated in the paper."

Q&A:
- Answers must be grounded in the uploaded paper. Instruct the model to say when the paper does not contain the answer.
- Stream responses to the frontend.
- When RAG is used, return the source chunks or page numbers used for each answer so the UI can show them.

Credibility and reporting signals:
- Process credibility in the background without blocking the upload or summary response.
- External network transmission constraints:
  * Only outbound queries to the OpenAlex Works API (`api.openalex.org`) using strictly the extracted document Title or DOI string are permitted.
  * The document body text, extracted chunks, chat history, and user IDs must NEVER be sent to external services.
- Dynamic header metadata extraction:
  * The dynamic header extraction uses an internal structured call on text already parsed by the application. It receives STRICTLY the isolated Page 1 header block (never the document body) and does not transmit data to external third parties.

## Things to avoid

- Do not send the paper to any service other than the configured LLM provider.
- Do not transmit document body text, extracted chunks, chat history, or user IDs to external verification services (such as OpenAlex or other registries). Only Title or DOI string may be queried.
- Do not store uploaded PDFs permanently unless a feature needs them. Keep them in a temp directory and clean up.
- Do not expose API keys to the frontend. All LLM calls happen in the backend.
- Do not rewrite working code for style alone.
- Authentication is in scope: email and password sign-in with JWT in an HttpOnly cookie. Users are stored in SQLite. Every document, summary, and chat is scoped to the user who uploaded it.
- Do not store passwords in plain text. Do not log passwords, tokens, or the secret key.
- Do not invent citations, page numbers, or quotes. If the source location is unknown, omit it.
- Do not send uploaded papers to any third-party converter. External tools may be linked, but the user uploads to them directly.

## Testing expectations

- Backend: unit tests for `pdf_parser`, the summary schema validation, and the cache. Mock the LLM client in tests; never make real API calls in the test suite.
- Frontend: at minimum, a smoke test that the upload page and summary view render with fixture data.
- Include at least two sample research papers in `backend/tests/fixtures/` for manual testing.

## Definition of done

A change is done when:
1. The feature works end to end in the dev servers.
2. Type check, lint, and tests pass.
3. `.env.example` and this file are updated if config or structure changed.
4. The README reflects any user-visible behavior change.

When you finish a task, report what changed, what you tested, and anything you were unable to verify.
