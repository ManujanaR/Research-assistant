import logging

import bcrypt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.user import User

logger = logging.getLogger(__name__)


def normalize_email(email: str) -> str:
    """Normalise an email address to stripped lowercase."""
    return email.strip().lower()


def hash_password(password: str) -> str:
    """Hash a plain text password using bcrypt with a salt."""
    salt = bcrypt.gensalt()
    pw_bytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(pw_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except (ValueError, TypeError) as e:
        logger.warning("Error during password verification: %s", type(e).__name__)
        return False


def get_user_by_email(db: Session, email: str) -> User | None:
    """Look up a user by email, normalising to lowercase."""
    norm_email = normalize_email(email)
    return db.query(User).filter(User.email == norm_email).first()


def create_user(db: Session, email: str, password: str) -> User:
    """Create and persist a new user with bcrypt-hashed password."""
    norm_email = normalize_email(email)
    pw_hash = hash_password(password)
    user = User(
        email=norm_email,
        password_hash=pw_hash,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Created user account for email: %s", norm_email)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    """Authenticate a user by email and password, returning User if valid."""
    user = get_user_by_email(db, email)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def validate_display_name(name: str | None) -> str | None:
    """Validate and clean display name according to profile rules."""
    if name is None:
        return None
    trimmed = name.strip()
    if not trimmed:
        return None
    if len(trimmed) > 60:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Display name must be 60 characters or fewer.",
        )
    for ch in trimmed:
        if not (ch.isalnum() or ch in (" ", ".", "'", "-")):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Display name contains characters that are not allowed.",
            )
    return trimmed


def update_display_name(
    user: User,
    name: str | None,
    db: Session | None = None,
) -> User:
    """Update user's display name, trimming whitespace and treating empty as clearing."""
    cleaned = validate_display_name(name)
    user.display_name = cleaned
    session = db or Session.object_session(user)
    if session is not None:
        session.commit()
        session.refresh(user)
    return user


def change_password(
    user: User,
    current_password: str,
    new_password: str,
    db: Session | None = None,
) -> User:
    """Verify current password, validate new password, rehash, and increment token_version."""
    if not verify_password(current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )
    if len(new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters.",
        )
    if current_password == new_password or verify_password(
        new_password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="New password must be different from current password.",
        )

    user.password_hash = hash_password(new_password)
    user.token_version = (user.token_version or 0) + 1
    session = db or Session.object_session(user)
    if session is not None:
        session.commit()
        session.refresh(user)
    return user
