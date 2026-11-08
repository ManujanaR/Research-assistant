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


class ProfileResponse(BaseModel):
    """User profile response schema."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str = Field(
        ...,
        description="Unique user identifier (UUID).",
    )
    email: str = Field(
        ...,
        description="Normalised user email address.",
    )
    display_name: str | None = Field(
        None,
        description="User display name, or null if unset.",
    )


class UpdateProfileRequest(BaseModel):
    """Update user profile request schema."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(
        None,
        description="Optional display name (1-60 chars after trim, letters, digits, spaces, ., ', -).",
    )


class ChangePasswordRequest(BaseModel):
    """Change password request schema."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(
        ...,
        description="Current user password.",
    )
    new_password: str = Field(
        ...,
        description="New user password (minimum 8 characters).",
    )
