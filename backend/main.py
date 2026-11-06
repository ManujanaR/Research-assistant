import os
import uuid
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pypdf.errors import PdfReadError

try:
    from chunker import chunk_pages
    from pdf_parser import parse_pdf
except ImportError:
    from backend.chunker import chunk_pages
    from backend.pdf_parser import parse_pdf

app = FastAPI(title="Research Assistant API")

env_path = os.path.join(os.path.dirname(__file__), ".env")
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)) -> dict[str, Any]:
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

    return {
        "doc_id": doc_id,
        "pages": len(pages),
        "chunks": len(chunks),
    }
