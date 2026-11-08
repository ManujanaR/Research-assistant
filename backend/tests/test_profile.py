"""Tests for user profile, display name, password change, session revocation, and migrations."""

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import Base, get_db, init_db
from app.main import app
from app.models.user import User
from app.services.auth_service import create_user
from app.services.rate_limiter import login_rate_limiter


@pytest.fixture
def test_db_session(
    tmp_path: Path,
) -> Generator[tuple[Session, Engine, Any], None, None]:
    """Create a temporary SQLite database in tmp_path for testing."""
    login_rate_limiter.reset_all()
    test_db_file = tmp_path / "test_profile.db"
    test_db_url = f"sqlite:///{test_db_file}"
    engine = create_engine(
        test_db_url,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    testing_session_factory = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )

    session = testing_session_factory()
    try:
        yield session, engine, testing_session_factory
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        login_rate_limiter.reset_all()


@pytest.fixture
def client(
    test_db_session: tuple[Session, Engine, Any],
) -> Generator[TestClient, None, None]:
    """TestClient with get_db overridden to use temporary SQLite test session."""
    _, _, testing_session_factory = test_db_session

    def override_get_db() -> Generator[Session, None, None]:
        session = testing_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_profile_for_signed_in_user(
    client: TestClient, test_db_session: tuple[Session, Engine, Any]
) -> None:
    """A signed-in user can fetch their profile."""
    db, _, _ = test_db_session
    create_user(db, email="ada@example.com", password="password123")

    signin_resp = client.post(
        "/api/auth/signin",
        json={"email": "ada@example.com", "password": "password123"},
    )
    assert signin_resp.status_code == 200

    profile_resp = client.get("/api/auth/profile")
    assert profile_resp.status_code == 200
    data = profile_resp.json()
    assert data["email"] == "ada@example.com"
    assert data["display_name"] is None
    assert "id" in data


def test_profile_401_without_a_cookie(client: TestClient) -> None:
    """Requesting profile without a cookie returns 401."""
    resp = client.get("/api/auth/profile")
    assert resp.status_code == 401


def test_name_set_trimmed_and_cleared(
    client: TestClient, test_db_session: tuple[Session, Engine, Any]
) -> None:
    """Display name can be set, is trimmed, and can be cleared with empty or whitespace."""
    db, _, _ = test_db_session
    create_user(db, email="trim@example.com", password="password123")

    client.post(
        "/api/auth/signin",
        json={"email": "trim@example.com", "password": "password123"},
    )

    # Set name with padding whitespace
    patch_resp = client.patch(
        "/api/auth/profile",
        json={"display_name": "  Grace Hopper-O'Conner. 1  "},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["display_name"] == "Grace Hopper-O'Conner. 1"

    # Verify GET reflects the trimmed name
    get_resp = client.get("/api/auth/profile")
    assert get_resp.status_code == 200
    assert get_resp.json()["display_name"] == "Grace Hopper-O'Conner. 1"

    # Clear name using whitespace
    clear_resp = client.patch(
        "/api/auth/profile",
        json={"display_name": "   "},
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json()["display_name"] is None

    # Clear name using null
    clear_null_resp = client.patch(
        "/api/auth/profile",
        json={"display_name": None},
    )
    assert clear_null_resp.status_code == 200
    assert clear_null_resp.json()["display_name"] is None


def test_61_character_name_returns_422(
    client: TestClient, test_db_session: tuple[Session, Engine, Any]
) -> None:
    """A name with 61 characters returns 422 with the exact spec message."""
    db, _, _ = test_db_session
    create_user(db, email="longname@example.com", password="password123")

    client.post(
        "/api/auth/signin",
        json={"email": "longname@example.com", "password": "password123"},
    )

    resp = client.patch(
        "/api/auth/profile",
        json={"display_name": "a" * 61},
    )
    assert resp.status_code == 422
    assert "Display name must be 60 characters or fewer." in resp.text


def test_name_containing_script_returns_422(
    client: TestClient, test_db_session: tuple[Session, Engine, Any]
) -> None:
    """A name containing disallowed characters like <script> returns 422."""
    db, _, _ = test_db_session
    create_user(db, email="script@example.com", password="password123")

    client.post(
        "/api/auth/signin",
        json={"email": "script@example.com", "password": "password123"},
    )

    resp = client.patch(
        "/api/auth/profile",
        json={"display_name": "<script>alert('xss')</script>"},
    )
    assert resp.status_code == 422
    assert "Display name contains characters that are not allowed." in resp.text


def test_changing_password_works_and_revokes_old_sessions(
    client: TestClient, test_db_session: tuple[Session, Engine, Any]
) -> None:
    """Changing password updates password, reissues caller session, invalidates old token, and allows new login."""
    db, _, _ = test_db_session
    create_user(db, email="pwd@example.com", password="oldpassword123")

    # Sign in to get original token
    signin_resp = client.post(
        "/api/auth/signin",
        json={"email": "pwd@example.com", "password": "oldpassword123"},
    )
    assert signin_resp.status_code == 200
    old_cookie = client.cookies.get("auth_token")
    assert old_cookie is not None

    # Change password
    change_resp = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "oldpassword123",
            "new_password": "newpassword456",
        },
    )
    assert change_resp.status_code == 200
    assert change_resp.json()["status"] == "ok"

    # Current session survives (cookie reissued with new token_version)
    current_profile_resp = client.get("/api/auth/profile")
    assert current_profile_resp.status_code == 200

    # An older token returns 401
    alien_client = TestClient(app)
    alien_client.cookies.set("auth_token", old_cookie)
    alien_resp = alien_client.get("/api/auth/profile")
    assert alien_resp.status_code == 401

    # Old password no longer signs in
    old_signin_resp = client.post(
        "/api/auth/signin",
        json={"email": "pwd@example.com", "password": "oldpassword123"},
    )
    assert old_signin_resp.status_code == 401

    # New password signs in successfully
    new_signin_resp = client.post(
        "/api/auth/signin",
        json={"email": "pwd@example.com", "password": "newpassword456"},
    )
    assert new_signin_resp.status_code == 200


def test_wrong_current_password_returns_401_with_exact_message(
    client: TestClient, test_db_session: tuple[Session, Engine, Any]
) -> None:
    """Wrong current password returns 401 with 'Current password is incorrect.'"""
    db, _, _ = test_db_session
    create_user(db, email="wrongpwd@example.com", password="password123")

    client.post(
        "/api/auth/signin",
        json={"email": "wrongpwd@example.com", "password": "password123"},
    )

    resp = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "incorrectpassword",
            "new_password": "newpassword123",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Current password is incorrect."


def test_new_password_equal_to_current_returns_422(
    client: TestClient, test_db_session: tuple[Session, Engine, Any]
) -> None:
    """New password equal to current password returns 422."""
    db, _, _ = test_db_session
    create_user(db, email="samepwd@example.com", password="password123")

    client.post(
        "/api/auth/signin",
        json={"email": "samepwd@example.com", "password": "password123"},
    )

    resp = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "password123",
            "new_password": "password123",
        },
    )
    assert resp.status_code == 422


def test_new_password_under_8_chars_returns_422(
    client: TestClient, test_db_session: tuple[Session, Engine, Any]
) -> None:
    """New password under 8 characters returns 422."""
    db, _, _ = test_db_session
    create_user(db, email="shortpwd@example.com", password="password123")

    client.post(
        "/api/auth/signin",
        json={"email": "shortpwd@example.com", "password": "password123"},
    )

    resp = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "password123",
            "new_password": "short",
        },
    )
    assert resp.status_code == 422


def test_repeated_wrong_change_password_attempts_return_429(
    client: TestClient, test_db_session: tuple[Session, Engine, Any]
) -> None:
    """Repeated wrong password attempts on change-password trigger 429 rate limit."""
    db, _, _ = test_db_session
    create_user(db, email="ratelimit@example.com", password="password123")

    client.post(
        "/api/auth/signin",
        json={"email": "ratelimit@example.com", "password": "password123"},
    )

    # 5 wrong attempts
    for _ in range(5):
        resp = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "wrongpassword",
                "new_password": "newpassword123",
            },
        )
        assert resp.status_code == 401

    # 6th attempt should be rate limited with 429
    blocked_resp = client.post(
        "/api/auth/change-password",
        json={
            "current_password": "wrongpassword",
            "new_password": "newpassword123",
        },
    )
    assert blocked_resp.status_code == 429
    assert "Too many attempts" in blocked_resp.text


def test_migration_keeps_existing_users_working(tmp_path: Path) -> None:
    """Startup migration adds display_name and token_version to existing table with existing users."""
    test_db_file = tmp_path / "legacy_users.db"
    engine = create_engine(f"sqlite:///{test_db_file}")

    # Create old table without display_name and token_version
    with engine.connect() as conn:
        conn.execute(
            text(
                """
            CREATE TABLE users (
                id VARCHAR(36) PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP NOT NULL
            )
        """
            )
        )
        conn.execute(
            text(
                """
            INSERT INTO users (id, email, password_hash, created_at)
            VALUES ('legacy-user-1', 'legacy@example.com', '$2b$12$e8Y59Gv83LzB5gD1N2e4xO9.w5mB0C2s7.l3', CURRENT_TIMESTAMP)
        """
            )
        )
        conn.commit()

    # Run migration
    init_db(engine)

    # Verify columns and data
    testing_session_factory = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    session = testing_session_factory()
    try:
        legacy_user = session.query(User).filter(User.id == "legacy-user-1").first()
        assert legacy_user is not None
        assert legacy_user.email == "legacy@example.com"
        assert legacy_user.display_name is None
        assert legacy_user.token_version == 0
    finally:
        session.close()
