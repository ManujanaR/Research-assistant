"""Pytest fixtures for authenticated backend API tests."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.session import Base, get_db
from app.main import app
from app.services.ownership_service import record_owner
from app.services.rate_limiter import login_rate_limiter


class AuthenticatedTestClient(TestClient):
    """TestClient that holds authenticated user identity and document ownership helper."""

    user_id: str
    email: str
    db: Session

    def record_ownership(self, doc_hash: str) -> None:
        """Record ownership of doc_hash for this client's user in the test database."""
        record_owner(doc_hash, self.user_id, db=self.db)


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    """Create an isolated in-memory SQLite database sharing a StaticPool connection."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def auth_client(
    test_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[AuthenticatedTestClient, None, None]:
    """Create a temporary SQLite database, sign up a test user, sign in, and return TestClient holding the auth cookie."""
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-auth-secret-key-32-bytes-long")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-key")
    get_settings.cache_clear()
    login_rate_limiter.reset_all()

    def override_get_db() -> Generator[Session, None, None]:
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    email = "testuser@example.com"
    password = "Password123!"

    client = AuthenticatedTestClient(app)

    # Real sign-up and sign-in through routes
    signup_resp = client.post(
        "/api/auth/signup", json={"email": email, "password": password}
    )
    assert signup_resp.status_code == 201, (
        f"conftest auth_client signup failed: {signup_resp.text}"
    )
    user_id = signup_resp.json()["id"]

    signin_resp = client.post(
        "/api/auth/signin", json={"email": email, "password": password}
    )
    assert signin_resp.status_code == 200, (
        f"conftest auth_client signin failed: {signin_resp.text}"
    )
    assert "auth_token" in client.cookies

    client.user_id = user_id
    client.email = email
    client.db = test_db

    yield client

    login_rate_limiter.reset_all()
    get_settings.cache_clear()


@pytest.fixture
def auth_client_other(
    test_db: Session,
    auth_client: AuthenticatedTestClient,
) -> Generator[AuthenticatedTestClient, None, None]:
    """Create a second authenticated test user for ownership tests."""
    email = "otheruser@example.com"
    password = "Password456!"

    client = AuthenticatedTestClient(app)

    signup_resp = client.post(
        "/api/auth/signup", json={"email": email, "password": password}
    )
    assert signup_resp.status_code == 201, (
        f"conftest auth_client_other signup failed: {signup_resp.text}"
    )
    user_id = signup_resp.json()["id"]

    signin_resp = client.post(
        "/api/auth/signin", json={"email": email, "password": password}
    )
    assert signin_resp.status_code == 200, (
        f"conftest auth_client_other signin failed: {signin_resp.text}"
    )
    assert "auth_token" in client.cookies

    client.user_id = user_id
    client.email = email
    client.db = test_db

    yield client
