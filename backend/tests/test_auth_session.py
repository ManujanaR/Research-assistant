"""Tests for session management, /me, signout, and login rate limiting."""

import base64
import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.session import Base, get_db
from app.main import app
from app.models.user import User
from app.services.auth_service import hash_password
from app.services.rate_limiter import login_rate_limiter
from app.services.token_service import create_access_token


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    """Create a temporary in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
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
def client(test_db: Session) -> Generator[TestClient, None, None]:
    """TestClient with overridden get_db dependency."""

    def override_get_db() -> Generator[Session, None, None]:
        try:
            yield test_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def clean_rate_limiter() -> Generator[None, None, None]:
    """Ensure rate limiter state is reset before and after every test."""
    login_rate_limiter.reset_all()
    yield
    login_rate_limiter.reset_all()


@pytest.fixture
def registered_user(test_db: Session) -> User:
    """Insert a known user into the test database."""
    user = User(
        email="researcher@example.com",
        password_hash=hash_password("SuperSecret123"),
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


def test_signin_sets_httponly_samesite_lax_cookie(
    client: TestClient, registered_user: User
) -> None:
    """Sign-in sets an HttpOnly cookie with SameSite=Lax and correct user payload."""
    response = client.post(
        "/api/auth/signin",
        json={"email": "researcher@example.com", "password": "SuperSecret123"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "researcher@example.com"

    # Verify cookie presence and attributes in Set-Cookie header
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any("auth_token=" in h for h in set_cookie_headers)
    cookie_header = next(h for h in set_cookie_headers if "auth_token=" in h)
    assert "httponly" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()


def test_me_with_cookie_returns_user_and_without_returns_401(
    client: TestClient, registered_user: User
) -> None:
    """/me with valid cookie returns user profile; without it, returns 401."""
    # Without cookie
    resp_unauth = client.get("/api/auth/me")
    assert resp_unauth.status_code == 401
    assert resp_unauth.json()["detail"] == "Not authenticated"

    # Sign in to obtain session cookie in client
    resp_login = client.post(
        "/api/auth/signin",
        json={"email": "researcher@example.com", "password": "SuperSecret123"},
    )
    assert resp_login.status_code == 200

    # With session cookie
    resp_me = client.get("/api/auth/me")
    assert resp_me.status_code == 200
    assert resp_me.json() == {
        "id": registered_user.id,
        "email": "researcher@example.com",
    }


def test_expired_token_returns_401(client: TestClient, registered_user: User) -> None:
    """An expired token in the cookie returns 401."""
    expired_token = create_access_token(
        user_id=registered_user.id,
        expires_minutes=-10,
    )
    client.cookies.set("auth_token", expired_token)
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert "token" in response.json()["detail"].lower()


def test_token_signed_with_different_key_returns_401(
    client: TestClient, registered_user: User
) -> None:
    """A token signed with a different key returns 401."""
    alien_token = create_access_token(
        user_id=registered_user.id,
        secret_key="completely-different-signing-secret-key-32b",
    )
    client.cookies.set("auth_token", alien_token)
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert "token" in response.json()["detail"].lower()


def test_token_with_alg_none_returns_401(
    client: TestClient, registered_user: User
) -> None:
    """A forged token with alg: none returns 401."""
    header = {"alg": "none", "typ": "JWT"}
    payload = {
        "sub": registered_user.id,
        "exp": int((datetime.now(UTC) + timedelta(minutes=10)).timestamp()),
    }
    h_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    p_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    none_token = f"{h_b64}.{p_b64}."

    client.cookies.set("auth_token", none_token)
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert "token" in response.json()["detail"].lower()


def test_signout_clears_cookie_and_me_returns_401(
    client: TestClient, registered_user: User
) -> None:
    """Sign-out clears session cookie and subsequent /me returns 401."""
    login_resp = client.post(
        "/api/auth/signin",
        json={"email": "researcher@example.com", "password": "SuperSecret123"},
    )
    assert login_resp.status_code == 200

    # Ensure /me works
    me_resp = client.get("/api/auth/me")
    assert me_resp.status_code == 200

    # Call signout
    signout_resp = client.post("/api/auth/signout")
    assert signout_resp.status_code == 200

    # TestClient processes Set-Cookie to clear/expire cookie
    me_after = client.get("/api/auth/me")
    assert me_after.status_code == 401


def test_after_5_failed_signins_next_attempt_returns_429(
    client: TestClient, registered_user: User
) -> None:
    """After 5 failed attempts, the 6th attempt returns 429 even with correct credentials."""
    for _ in range(5):
        resp = client.post(
            "/api/auth/signin",
            json={"email": "researcher@example.com", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Email or password is incorrect."

    # 6th attempt with CORRECT password
    blocked_resp = client.post(
        "/api/auth/signin",
        json={"email": "researcher@example.com", "password": "SuperSecret123"},
    )
    assert blocked_resp.status_code == 429
    assert (
        blocked_resp.json()["detail"]
        == "Too many attempts. Try again in a few minutes."
    )


def test_successful_signin_resets_failure_count(
    client: TestClient, registered_user: User
) -> None:
    """A successful signin resets the limiter failure count."""
    # 4 failed attempts (under threshold of 5)
    for _ in range(4):
        resp = client.post(
            "/api/auth/signin",
            json={"email": "researcher@example.com", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401

    # Successful attempt resets counter
    success_resp = client.post(
        "/api/auth/signin",
        json={"email": "researcher@example.com", "password": "SuperSecret123"},
    )
    assert success_resp.status_code == 200

    # Another 4 failed attempts should not trigger 429
    for _ in range(4):
        resp = client.post(
            "/api/auth/signin",
            json={"email": "researcher@example.com", "password": "WrongPassword!"},
        )
        assert resp.status_code == 401


def test_wrong_password_and_unknown_email_and_rate_limit_do_not_reveal_account_existence(
    client: TestClient, registered_user: User
) -> None:
    """Failed login and rate limiting yield identical messages whether email exists or not."""
    # Wrong password for existing user
    resp_existing = client.post(
        "/api/auth/signin",
        json={"email": "researcher@example.com", "password": "WrongPassword!"},
    )
    # Unknown user
    resp_unknown = client.post(
        "/api/auth/signin",
        json={"email": "nobody@example.com", "password": "WrongPassword!"},
    )
    assert resp_existing.status_code == 401
    assert resp_unknown.status_code == 401
    assert resp_existing.json() == resp_unknown.json()
    assert resp_existing.json()["detail"] == "Email or password is incorrect."

    # Trigger rate limit on unknown user
    for _ in range(4):
        client.post(
            "/api/auth/signin",
            json={"email": "nobody@example.com", "password": "WrongPassword!"},
        )
    resp_rate_limited = client.post(
        "/api/auth/signin",
        json={"email": "nobody@example.com", "password": "WrongPassword!"},
    )
    assert resp_rate_limited.status_code == 429
    assert (
        resp_rate_limited.json()["detail"]
        == "Too many attempts. Try again in a few minutes."
    )


def test_production_cookie_has_secure_flag(
    client: TestClient, registered_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When ENVIRONMENT=production, the auth cookie includes the Secure flag."""
    settings = get_settings()
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(
        settings,
        "auth_secret_key",
        "production-secret-key-at-least-32-chars-long",
    )

    response = client.post(
        "/api/auth/signin",
        json={"email": "researcher@example.com", "password": "SuperSecret123"},
    )
    assert response.status_code == 200
    set_cookie_headers = response.headers.get_list("set-cookie")
    cookie_header = next(h for h in set_cookie_headers if "auth_token=" in h)
    assert "secure" in cookie_header.lower()
