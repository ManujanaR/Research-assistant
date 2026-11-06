import os
import uuid
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pypdf.errors import PdfReadError

try:
    from chunker import chunk_pages
    from llm import answer_question, embed_texts
    from pdf_parser import parse_pdf
    from retriever import has_index, search, store_chunks
    from summarizer import summarize_paper
except ImportError:
    from backend.chunker import chunk_pages
    from backend.llm import answer_question, embed_texts
    from backend.pdf_parser import parse_pdf
    from backend.retriever import has_index, search, store_chunks
    from backend.summarizer import summarize_paper

app = FastAPI(title="Research Assistant API")

for env_path in [
    os.path.join(os.path.dirname(__file__), ".env"),
    os.path.join(os.path.dirname(__file__), "..", ".env"),
]:
    if os.path.isfile(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    k, v = stripped.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

allowed_origins_raw = os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:5173"
).strip()
allowed_origins = [
    origin.strip()
    for origin in allowed_origins_raw.split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

latest_summary: dict[str, str] | None = None
latest_filename: str | None = None
stored_pages: list[dict[str, Any]] = []
stored_sections: dict[int, str] = {}


class AskRequest(BaseModel):
    question: str = ""


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)) -> dict[str, Any]:
    global latest_summary, latest_filename, stored_pages, stored_sections

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400, detail="Only PDF files are supported."
        )

    file_bytes = await file.read()
    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(
            status_code=400, detail="Uploaded file is not a valid PDF."
        )

    try:
        pages = parse_pdf(file_bytes)
    except PdfReadError as err:
        raise HTTPException(
            status_code=400, detail=f"Failed to parse PDF: {str(err)}"
        )

    chunks = chunk_pages(pages)
    doc_id = str(uuid.uuid4())

    full_text = "\n\n".join(str(p["text"]) for p in pages if p.get("text"))
    try:
        summary = summarize_paper(full_text)
        chunk_texts = [str(c["text"]) for c in chunks]
        vectors = embed_texts(chunk_texts)
        store_chunks(chunks, vectors)
    except (ValueError, RuntimeError) as err:
        raise HTTPException(
            status_code=500, detail=f"Processing failed: {str(err)}"
        )

    latest_summary = summary
    latest_filename = file.filename or "document.pdf"
    stored_pages = pages

    stored_sections = {}
    for c in chunks:
        p_num = int(c["page"])
        if p_num not in stored_sections and c.get("section"):
            stored_sections[p_num] = str(c["section"])

    curr_sec = "Document"
    for p in pages:
        p_num = int(p["page"])
        if p_num in stored_sections:
            curr_sec = stored_sections[p_num]
        else:
            stored_sections[p_num] = curr_sec

    return {
        "doc_id": doc_id,
        "file_name": latest_filename,
        "pages": len(pages),
        "total_pages": len(pages),
        "chunks": len(chunks),
        "summary": summary,
    }


@app.get("/document")
def get_document() -> dict[str, Any]:
    if not stored_pages:
        raise HTTPException(
            status_code=404, detail="No paper has been uploaded yet."
        )
    return {
        "file_name": latest_filename or "document.pdf",
        "total_pages": len(stored_pages),
    }


@app.get("/pages/{page_number}")
def get_page(page_number: int) -> dict[str, Any]:
    if not stored_pages:
        raise HTTPException(
            status_code=404, detail="No paper has been uploaded yet."
        )
    if page_number < 1 or page_number > len(stored_pages):
        raise HTTPException(
            status_code=404, detail=f"Page {page_number} not found."
        )
    page_data = stored_pages[page_number - 1]
    section = stored_sections.get(page_number, "Document")
    return {
        "page": page_number,
        "text": page_data.get("text", ""),
        "section": section,
    }


@app.get("/summary")
def get_summary() -> dict[str, str]:
    if latest_summary is None:
        raise HTTPException(
            status_code=404, detail="No paper has been uploaded yet."
        )
    return latest_summary


@app.post("/ask")
def ask(req: AskRequest) -> dict[str, Any]:
    if not req.question or not req.question.strip():
        raise HTTPException(
            status_code=400, detail="Question cannot be empty."
        )

    if not has_index():
        raise HTTPException(
            status_code=404, detail="No paper has been uploaded yet."
        )

    question_clean = req.question.strip()
    try:
        q_vectors = embed_texts([question_clean])
    except (ValueError, RuntimeError) as err:
        raise HTTPException(
            status_code=500, detail=f"Question embedding failed: {str(err)}"
        )

    if not q_vectors:
        raise HTTPException(
            status_code=500, detail="Failed to embed question."
        )

    top_chunks = search(q_vectors[0], top_k=4)

    try:
        answer = answer_question(question_clean, top_chunks)
    except (ValueError, RuntimeError) as err:
        raise HTTPException(
            status_code=500, detail=f"Question answering failed: {str(err)}"
        )

    sources = [
        {
            "section": c["section"],
            "page": c["page"],
            "snippet": c["text"][:200],
            "text": c["text"],
        }
        for c in top_chunks
    ]

    return {
        "answer": answer,
        "sources": sources,
    }
