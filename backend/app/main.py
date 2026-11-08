import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.credibility import router as credibility_router
from app.api.export import router as export_router
from app.api.summary import router as summary_router
from app.api.upload import router as upload_router
from app.core.config import get_settings
from app.db.session import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager for startup and shutdown events."""
    logger.info("Initializing database tables at startup...")
    init_db()
    yield


app = FastAPI(
    title="Mitra Research Assistant API",
    version="1.0.0",
    description="Backend API for research paper upload, structured summary, and grounded Q&A.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(summary_router)
app.include_router(chat_router)
app.include_router(credibility_router)
app.include_router(export_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint to verify backend service availability."""
    return {"status": "ok"}
