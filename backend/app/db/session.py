import logging
from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import BACKEND_DIR, get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for SQLAlchemy declarative models."""


def _ensure_data_directory(database_url: str) -> None:
    """Ensure the target directory for SQLite database file exists."""
    # Ensure default data/ directory in backend exists
    default_data_dir = BACKEND_DIR / "data"
    default_data_dir.mkdir(parents=True, exist_ok=True)

    if database_url.startswith("sqlite:///"):
        raw_path = database_url.replace("sqlite:///", "")
        if raw_path and raw_path != ":memory:":
            file_path = Path(raw_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)


def get_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine configured for the provided or default database URL."""
    url = database_url or get_settings().database_url
    _ensure_data_directory(url)
    connect_args: dict[str, Any] = (
        {"check_same_thread": False} if "sqlite" in url else {}
    )
    return create_engine(url, connect_args=connect_args)


engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def run_migrations(target_engine: Engine | None = None) -> None:
    """Run lightweight schema migrations on startup to add missing columns."""
    eng = target_engine or engine
    with eng.connect() as conn:
        inspector = inspect(conn)
        table_names = inspector.get_table_names()
        if "users" in table_names:
            columns = {col["name"] for col in inspector.get_columns("users")}
            if "display_name" not in columns:
                conn.execute(
                    text("ALTER TABLE users ADD COLUMN display_name VARCHAR(60)")
                )
                logger.info("Migrated: added display_name column to users table.")
            if "token_version" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"
                    )
                )
                logger.info("Migrated: added token_version column to users table.")
            conn.commit()

        if "document_ownership" in table_names:
            pk_info = inspector.get_pk_constraint("document_ownership")
            pk_cols = pk_info.get("constrained_columns", [])
            if "owner_id" not in pk_cols:
                logger.info(
                    "Migrating document_ownership to composite primary key (doc_hash, owner_id)..."
                )
                conn.execute(
                    text(
                        """
                        CREATE TABLE document_ownership_tmp (
                            doc_hash VARCHAR(64) NOT NULL,
                            owner_id VARCHAR(36) NOT NULL,
                            created_at DATETIME NOT NULL,
                            PRIMARY KEY (doc_hash, owner_id),
                            FOREIGN KEY(owner_id) REFERENCES users (id)
                        )
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        INSERT OR IGNORE INTO document_ownership_tmp (doc_hash, owner_id, created_at)
                        SELECT doc_hash, owner_id, created_at FROM document_ownership
                        """
                    )
                )
                conn.execute(text("DROP TABLE document_ownership"))
                conn.execute(
                    text(
                        "ALTER TABLE document_ownership_tmp RENAME TO document_ownership"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX ix_document_ownership_doc_hash ON document_ownership (doc_hash)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX ix_document_ownership_owner_id ON document_ownership (owner_id)"
                    )
                )
                conn.commit()
                logger.info(
                    "Migrated: updated document_ownership to composite primary key."
                )


def init_db(target_engine: Engine | None = None) -> None:
    """Create all database tables on the specified or default engine and run migrations."""
    eng = target_engine or engine
    Base.metadata.create_all(bind=eng)
    run_migrations(eng)
    logger.info("Database tables initialized successfully.")


def get_db() -> Generator[Session, None, None]:
    """Yield a database session from the session factory."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
