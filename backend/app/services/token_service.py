"""JWT token generation and verification service."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt.exceptions import PyJWTError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
DEV_FALLBACK_SECRET = "dev-insecure-secret-key-change-me-at-least-32-bytes-long"


def _get_signing_key(override_key: str | None = None) -> str:
    """Retrieve secret key, validating production requirements."""
    if override_key:
        return override_key
    settings = get_settings()
    if settings.auth_secret_key:
        return settings.auth_secret_key
    if settings.environment.lower() == "production":
        raise ValueError("AUTH_SECRET_KEY is required in production environment.")
    return DEV_FALLBACK_SECRET


def create_access_token(
    user_id: str,
    token_version: int = 0,
    expires_minutes: int | None = None,
    secret_key: str | None = None,
) -> str:
    """Generate a signed JWT token containing user_id and token_version."""
    settings = get_settings()
    key = _get_signing_key(secret_key)
    ttl = (
        expires_minutes
        if expires_minutes is not None
        else settings.auth_token_ttl_minutes
    )
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=ttl)
    payload = {
        "sub": str(user_id),
        "token_version": int(token_version),
        "v": int(token_version),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, key, algorithm=ALGORITHM)


def decode_access_token(
    token: str,
    secret_key: str | None = None,
) -> dict[str, Any] | None:
    """Decode and validate a JWT access token, returning its payload dict or None."""
    if not token or not isinstance(token, str):
        return None

    try:
        key = _get_signing_key(secret_key)
        payload = jwt.decode(
            token,
            key,
            algorithms=[ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        return payload
    except (PyJWTError, ValueError, TypeError) as exc:
        logger.debug("Access token decoding failed: %s", type(exc).__name__)
        return None


def verify_access_token(
    token: str,
    secret_key: str | None = None,
) -> str | None:
    """Verify a JWT access token and return the user ID (sub claim).

    Rejects any token with an unexpected algorithm (e.g., 'none', asymmetric algs),
    expired signature, invalid key, or malformed structure. Never logs the full token.
    """
    payload = decode_access_token(token, secret_key=secret_key)
    if not payload:
        return None
    user_id = payload.get("sub")
    if not user_id or not isinstance(user_id, str):
        return None
    return user_id
