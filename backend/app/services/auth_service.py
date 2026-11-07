import logging

import bcrypt
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
