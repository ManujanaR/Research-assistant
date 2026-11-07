import logging
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db.session import Base, get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def test_db_session(
    tmp_path: Path,
) -> Generator[tuple[Session, Engine, Any], None, None]:
    """Create a temporary SQLite database in tmp_path for testing."""
    test_db_file = tmp_path / "test_auth.db"
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


def test_signup_returns_201_with_lowercase_email(client: TestClient) -> None:
    """Sign-up returns 201 with the lowercase email."""
    response = client.post(
        "/api/auth/signup",
        json={"email": "researcher@example.com", "password": "securepassword123"},
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert len(data["id"]) > 0
    assert data["email"] == "researcher@example.com"


def test_uppercase_email_is_stored_in_lowercase(
    client: TestClient, test_db_session: tuple[Session, Engine, Any]
) -> None:
    """An uppercase email is stored in lowercase."""
    session, _, _ = test_db_session
    response = client.post(
        "/api/auth/signup",
        json={
            "email": "UPPERCASE_RESEARCHER@EXAMPLE.COM",
            "password": "securepassword123",
        },
    )
    assert response.status_code == 201
    assert response.json()["email"] == "uppercase_researcher@example.com"

    # Query the database directly to verify stored column value
    db_user = (
        session.query(User)
        .filter(User.email == "uppercase_researcher@example.com")
        .first()
    )
    assert db_user is not None
    assert db_user.email == "uppercase_researcher@example.com"


def test_duplicate_email_returns_409_with_exact_message(
    client: TestClient,
) -> None:
    """A duplicate email returns 409 with the exact message."""
    first_res = client.post(
        "/api/auth/signup",
        json={"email": "duplicate@example.com", "password": "password123"},
    )
    assert first_res.status_code == 201

    # Attempt to sign up again with same email
    dup_res = client.post(
        "/api/auth/signup",
        json={"email": "duplicate@example.com", "password": "anotherpassword123"},
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["detail"] == "An account with this email already exists."

    # Also verify case-insensitive duplicate rejection
    dup_upper_res = client.post(
        "/api/auth/signup",
        json={"email": "DUPLICATE@EXAMPLE.COM", "password": "anotherpassword123"},
    )
    assert dup_upper_res.status_code == 409
    assert (
        dup_upper_res.json()["detail"] == "An account with this email already exists."
    )


def test_password_under_8_characters_returns_422(client: TestClient) -> None:
    """A password under 8 characters returns 422."""
    response = client.post(
        "/api/auth/signup",
        json={"email": "shortpw@example.com", "password": "short"},
    )
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data


def test_stored_hash_is_not_password_and_starts_with_2b(
    client: TestClient, test_db_session: tuple[Session, Engine, Any]
) -> None:
    """The stored hash is not the password and starts with $2b$."""
    session, _, _ = test_db_session
    plain_password = "my_super_secret_pw_123"

    response = client.post(
        "/api/auth/signup",
        json={"email": "hash_check@example.com", "password": plain_password},
    )
    assert response.status_code == 201

    user_id = response.json()["id"]
    db_user = session.query(User).filter(User.id == user_id).first()
    assert db_user is not None
    assert db_user.password_hash != plain_password
    assert db_user.password_hash.startswith("$2b$")


def test_correct_signin_returns_200_with_user(client: TestClient) -> None:
    """Correct sign-in returns 200 with the user."""
    signup_res = client.post(
        "/api/auth/signup",
        json={"email": "login_user@example.com", "password": "validpassword123"},
    )
    assert signup_res.status_code == 201

    signin_res = client.post(
        "/api/auth/signin",
        json={"email": "login_user@example.com", "password": "validpassword123"},
    )
    assert signin_res.status_code == 200
    data = signin_res.json()
    assert data["id"] == signup_res.json()["id"]
    assert data["email"] == "login_user@example.com"

    # Also test case-insensitive email sign-in
    upper_signin_res = client.post(
        "/api/auth/signin",
        json={"email": "LOGIN_USER@EXAMPLE.COM", "password": "validpassword123"},
    )
    assert upper_signin_res.status_code == 200
    assert upper_signin_res.json()["email"] == "login_user@example.com"


def test_wrong_password_and_unknown_email_both_return_401_with_same_message(
    client: TestClient,
) -> None:
    """Wrong password and unknown email both return 401 with the same message."""
    expected_message = "Email or password is incorrect."

    # Register legitimate user
    signup_res = client.post(
        "/api/auth/signup",
        json={"email": "existing_user@example.com", "password": "correctpassword123"},
    )
    assert signup_res.status_code == 201

    # Case 1: Existing email, wrong password
    wrong_pw_res = client.post(
        "/api/auth/signin",
        json={"email": "existing_user@example.com", "password": "wrongpassword999"},
    )
    assert wrong_pw_res.status_code == 401
    assert wrong_pw_res.json()["detail"] == expected_message

    # Case 2: Unknown email, arbitrary password
    unknown_email_res = client.post(
        "/api/auth/signin",
        json={"email": "does_not_exist@example.com", "password": "somepassword123"},
    )
    assert unknown_email_res.status_code == 401
    assert unknown_email_res.json()["detail"] == expected_message


def test_password_does_not_appear_in_any_response_or_captured_log_output(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The password does not appear in any response or captured log output."""
    secret_pw = "super_classified_pw_98765"

    with caplog.at_level(logging.DEBUG):
        # 1. Sign up
        signup_res = client.post(
            "/api/auth/signup",
            json={"email": "noleak@example.com", "password": secret_pw},
        )
        assert signup_res.status_code == 201
        assert secret_pw not in signup_res.text

        # 2. Sign in success
        signin_res = client.post(
            "/api/auth/signin",
            json={"email": "noleak@example.com", "password": secret_pw},
        )
        assert signin_res.status_code == 200
        assert secret_pw not in signin_res.text

        # 3. Sign in failure
        wrong_res = client.post(
            "/api/auth/signin",
            json={"email": "noleak@example.com", "password": "wrong_classified_pw_111"},
        )
        assert wrong_res.status_code == 401
        assert "wrong_classified_pw_111" not in wrong_res.text

        # 4. Captured log verification
        assert secret_pw not in caplog.text
        assert "wrong_classified_pw_111" not in caplog.text


def test_production_mode_with_empty_auth_secret_key_fails_at_startup() -> None:
    """Production mode with an empty AUTH_SECRET_KEY fails at startup."""
    with pytest.raises(
        ValueError, match="AUTH_SECRET_KEY is required in production environment"
    ):
        Settings(ENVIRONMENT="production", AUTH_SECRET_KEY="")

    with pytest.raises(
        ValueError, match="AUTH_SECRET_KEY is required in production environment"
    ):
        Settings(ENVIRONMENT="production", AUTH_SECRET_KEY="   ")

    # Non-empty key succeeds
    prod_valid = Settings(
        ENVIRONMENT="production",
        AUTH_SECRET_KEY="production-super-secret-key-12345",
    )
    assert prod_valid.environment == "production"
    assert prod_valid.auth_secret_key == "production-super-secret-key-12345"
