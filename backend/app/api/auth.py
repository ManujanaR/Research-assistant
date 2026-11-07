"""Authentication API routes: sign-up, sign-in, session verification, and sign-out."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import SignInRequest, SignUpRequest, UserResponse
from app.services.auth_service import (
    authenticate_user,
    create_user,
    get_user_by_email,
)
from app.services.rate_limiter import login_rate_limiter
from app.services.token_service import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE_NAME = "auth_token"


@router.post(
    "/signup",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def signup(
    request: SignUpRequest,
    db: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    """Create a new user account with hashed password and return the user profile."""
    existing_user = get_user_by_email(db, email=request.email)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = create_user(db, email=request.email, password=request.password)
    return UserResponse(id=user.id, email=user.email)


@router.post(
    "/signin",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate and sign in user",
)
async def signin(
    request: SignInRequest,
    http_request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    """Authenticate credentials, rate-limit failed attempts, and set HttpOnly session cookie."""
    client_ip = (
        http_request.client.host
        if http_request.client and http_request.client.host
        else "127.0.0.1"
    )
    norm_email = request.email.strip().lower()
    limiter_keys = [f"email:{norm_email}", f"ip:{client_ip}"]

    if login_rate_limiter.is_any_rate_limited(limiter_keys):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again in a few minutes.",
        )

    user = authenticate_user(db, email=request.email, password=request.password)
    if user is None:
        login_rate_limiter.record_failure(limiter_keys)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
        )

    login_rate_limiter.reset(limiter_keys)

    settings = get_settings()
    token = create_access_token(user_id=user.id)
    is_production = settings.environment.lower() == "production"

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=is_production,
        max_age=settings.auth_token_ttl_minutes * 60,
        path="/",
    )

    return UserResponse(id=user.id, email=user.email)


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get currently signed-in user",
)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return profile for user authenticated via session cookie."""
    return UserResponse(id=current_user.id, email=current_user.email)


@router.post(
    "/signout",
    status_code=status.HTTP_200_OK,
    summary="Sign out user and clear session cookie",
)
async def signout(
    response: Response,
) -> dict[str, str]:
    """Clear session cookie."""
    settings = get_settings()
    is_production = settings.environment.lower() == "production"
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=is_production,
    )
    return {"status": "ok"}
