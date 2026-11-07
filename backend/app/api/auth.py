import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import SignInRequest, SignUpRequest, UserResponse
from app.services.auth_service import (
    authenticate_user,
    create_user,
    get_user_by_email,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
    db: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    """Authenticate email and password and return the user profile without cookies in Step 1."""
    user = authenticate_user(db, email=request.email, password=request.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email or password is incorrect.",
        )

    return UserResponse(id=user.id, email=user.email)
