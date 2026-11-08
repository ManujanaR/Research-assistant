"""Authentication API routes: sign-up, sign-in, session verification, and sign-out."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ProfileResponse,
    SignInRequest,
    SignUpRequest,
    UpdateProfileRequest,
    UserResponse,
)
from app.services.auth_service import (
    authenticate_user,
    change_password,
    create_user,
    get_user_by_email,
    update_display_name,
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
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    """Create a new user account with hashed password and return the user profile with auth cookie."""
    existing_user = get_user_by_email(db, email=request.email)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = create_user(db, email=request.email, password=request.password)

    settings = get_settings()
    token = create_access_token(
        user_id=user.id,
        token_version=user.token_version,
    )
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
    token = create_access_token(
        user_id=user.id,
        token_version=user.token_version,
    )
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


@router.get(
    "/profile",
    response_model=ProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Get profile of signed-in user",
)
async def get_profile(
    current_user: Annotated[User, Depends(get_current_user)],
) -> ProfileResponse:
    """Return profile including display name for user authenticated via session cookie."""
    return ProfileResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
    )


@router.patch(
    "/profile",
    response_model=ProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="Update display name for signed-in user",
)
async def update_profile(
    request: UpdateProfileRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ProfileResponse:
    """Update user display name with trimming and rule enforcement."""
    updated_user = update_display_name(current_user, request.display_name, db=db)
    return ProfileResponse(
        id=updated_user.id,
        email=updated_user.email,
        display_name=updated_user.display_name,
    )


@router.post(
    "/change-password",
    status_code=status.HTTP_200_OK,
    summary="Change password and revoke other sessions",
)
async def change_password_endpoint(
    request: ChangePasswordRequest,
    response: Response,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str]:
    """Change password, increment token_version, and reissue caller session cookie."""
    limiter_key = f"user:{current_user.id}:change_password"
    if login_rate_limiter.is_rate_limited(limiter_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Try again in a few minutes.",
        )

    try:
        change_password(
            current_user,
            current_password=request.current_password,
            new_password=request.new_password,
            db=db,
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            login_rate_limiter.record_failure([limiter_key])
        raise

    login_rate_limiter.reset([limiter_key])

    settings = get_settings()
    token = create_access_token(
        user_id=current_user.id,
        token_version=current_user.token_version,
    )
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

    return {"status": "ok"}
