from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignUpRequest(BaseModel):
    """Sign up request schema."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(
        ...,
        description="User email address, formatted as a valid email.",
    )
    password: str = Field(
        ...,
        min_length=8,
        description="User password, minimum 8 characters.",
    )


class SignInRequest(BaseModel):
    """Sign in request schema."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(
        ...,
        description="User email address, formatted as a valid email.",
    )
    password: str = Field(
        ...,
        description="User plain password.",
    )


class UserResponse(BaseModel):
    """Public user response schema."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str = Field(
        ...,
        description="Unique user identifier (UUID).",
    )
    email: str = Field(
        ...,
        description="Normalised user email address.",
    )
