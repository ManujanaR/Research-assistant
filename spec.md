# SPEC.md: Research Assistant for PDFs

## Goal
A NotebookLM-style mini app. The user uploads one research paper (PDF). The app shows a structured summary, then answers questions about the paper using only its text, with citations to section and page.

## Stack
- Frontend: React (Vite), plain CSS
- Backend: Python 3.11+, FastAPI
- PDF text: pypdf
- LLM: Gemini (provider behind `llm.py` so it can be swapped)
- Retrieval: in-memory chunks with page and section metadata, cosine similarity with numpy. No database.

## Repo layout

research-assistant/
├── AGENTS.md
├── SPEC.md
├── README.md
├── backend/
│ ├── main.py # FastAPI app and routes only
│ ├── pdf_parser.py # PDF to pages of text
│ ├── chunker.py # text to chunks with page and section
│ ├── retriever.py # embed, store, search chunks
│ ├── summarizer.py # builds the five-section summary
│ ├── llm.py # the only file that calls the LLM API
│ ├── requirements.txt
│ └── .env.example
└── frontend/
└── src/
├── components/ # UploadPanel, SummaryView, ChatPanel, SourceViewer
└── App.jsx


## Phases

Build one phase per session. Each phase ends with a commit and a passing manual check.

### Phase 1: Backend foundation
- `GET /health` returns `{"status": "ok"}`
- `POST /upload` accepts one PDF, rejects other file types with a JSON error
- Extract text per page; chunk it with page number and section label
- Check: upload a real paper in `/docs`, see the page count and chunk count

### Phase 2: Summary
- After upload, generate a summary with exactly these keys:
  `title_authors_abstract`, `problem_statement`, `methodology`, `key_results`, `conclusion`
- Each value is built from the paper's text only. If a section is missing, the value is `"Not found in paper"`.
- `GET /summary` returns the stored summary
- Check: all five keys present and sensible for a real paper

### Phase 3: Question answering
- Embed chunks; `POST /ask` takes `{question}` and returns `{answer, sources}`
- Retrieve top-k chunks, answer only from them, cite section and page
- If the answer isn't in the paper, say so
- Check: three questions answered with citations; one unanswerable question handled

### Phase 4: Frontend
- Upload panel, five-section summary view, chat panel, clickable citations that show the source snippet
- Two-panel layout: summary or chat on one side, source viewer on the other
- Check: full flow works in the browser

### Phase 5: Polish
- Suggested questions after the summary (3 to 5, clickable)
- Clear error messages for: non-PDF, scanned PDF with no text, file too large, LLM failure
- README with setup steps that work on a fresh clone
- Check: fresh clone runs by following the README

## Done when
- A real paper produces all five summary sections
- Questions get cited answers; unanswerable ones say so
- Errors show clear messages
- A fresh clone runs from the README
- Commit history shows the phases