"""
Shared Pydantic schemas and validator mixins for cross-domain use.

This module consolidates duplicated schemas and validators found across
auth/schemas.py, users/schemas.py, and personalities/schemas.py.

Usage:
    from src.domains.shared.schemas import (
        TimezoneValidatorMixin,
        LanguageValidatorMixin,
        ThemeValidatorMixin,
        UserBase,
    )

    class MyUserSchema(UserBase):
        # Inherits all user fields and validators
        extra_field: str

    class MyRequestSchema(BaseModel, TimezoneValidatorMixin, LanguageValidatorMixin):
        timezone: str | None = None
        language: str | None = None
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.core.config import settings
from src.core.constants import PASSWORD_MAX_LENGTH, PASSWORD_MIN_LENGTH
from src.core.security import validate_password_strict
from src.core.validators import validate_timezone

# Valid theme values (centralized constants)
VALID_THEMES = ("light", "dark", "system")
VALID_COLOR_THEMES = ("default", "ocean", "forest", "sunset", "slate")
VALID_FONT_FAMILIES = (
    "system",  # Default (Inter)
    "noto-sans",  # Google's universal font
    "plus-jakarta-sans",  # Modern geometric
    "ibm-plex-sans",  # Technical clarity
    "geist",  # Vercel's design font
    "source-sans-pro",  # Adobe's accessible font
    "merriweather",  # Serif for reading
    "libre-baskerville",  # Classic serif
    "fira-code",  # Monospace with ligatures
)


class TimezoneValidatorMixin:
    """
    Mixin providing timezone field validation.

    Add to any Pydantic model that has a `timezone` field.
    """

    @field_validator("timezone", mode="before", check_fields=False)
    @classmethod
    def validate_timezone_field(cls, v: str | None) -> str | None:
        """Validate timezone is a valid IANA timezone name."""
        if v is None:
            return v

        if not validate_timezone(v):
            raise ValueError(
                f"Invalid timezone: {v}. Must be a valid IANA timezone name "
                "(e.g., 'Europe/Paris', 'America/New_York')"
            )

        return v


class LanguageValidatorMixin:
    """
    Mixin providing language field validation.

    Add to any Pydantic model that has a `language` field.
    """

    @field_validator("language", mode="before", check_fields=False)
    @classmethod
    def validate_language_field(cls, v: str | None) -> str | None:
        """Validate language is supported."""
        if v is None:
            return v

        if v not in settings.supported_languages:
            raise ValueError(
                f"Invalid language: {v}. Must be one of {', '.join(settings.supported_languages)}"
            )

        return v


class ThemeValidatorMixin:
    """
    Mixin providing theme field validation.

    Add to any Pydantic model that has `theme` or `color_theme` fields.
    """

    @field_validator("theme", mode="before", check_fields=False)
    @classmethod
    def validate_theme_field(cls, v: str | None) -> str | None:
        """Validate theme is valid."""
        if v is None:
            return v

        if v not in VALID_THEMES:
            raise ValueError(f"Invalid theme: {v}. Must be one of {', '.join(VALID_THEMES)}")

        return v

    @field_validator("color_theme", mode="before", check_fields=False)
    @classmethod
    def validate_color_theme_field(cls, v: str | None) -> str | None:
        """Validate color_theme is valid."""
        if v is None:
            return v

        if v not in VALID_COLOR_THEMES:
            raise ValueError(
                f"Invalid color_theme: {v}. Must be one of {', '.join(VALID_COLOR_THEMES)}"
            )

        return v


class FontFamilyValidatorMixin:
    """
    Mixin providing font_family field validation.

    Add to any Pydantic model that has a `font_family` field.
    """

    @field_validator("font_family", mode="before", check_fields=False)
    @classmethod
    def validate_font_family_field(cls, v: str | None) -> str | None:
        """Validate font_family is valid."""
        if v is None:
            return v

        if v not in VALID_FONT_FAMILIES:
            raise ValueError(
                f"Invalid font_family: {v}. Must be one of {', '.join(VALID_FONT_FAMILIES)}"
            )

        return v


# ============================================================================
# Image Generation Validation
# ============================================================================


class ImageGenerationValidatorMixin:
    """Mixin providing image generation field validation.

    Add to any Pydantic model that has image_generation_default_quality,
    image_generation_default_size, or image_generation_output_format fields.
    """

    @field_validator("image_generation_default_quality", mode="before", check_fields=False)
    @classmethod
    def validate_image_generation_quality(cls, v: str | None) -> str | None:
        """Validate image generation quality is supported."""
        if v is None:
            return v

        from src.core.constants import IMAGE_GENERATION_VALID_QUALITIES

        if v not in IMAGE_GENERATION_VALID_QUALITIES:
            raise ValueError(
                f"Invalid image quality: {v}. "
                f"Must be one of {', '.join(IMAGE_GENERATION_VALID_QUALITIES)}"
            )
        return v

    @field_validator("image_generation_default_size", mode="before", check_fields=False)
    @classmethod
    def validate_image_generation_size(cls, v: str | None) -> str | None:
        """Validate image generation size is supported."""
        if v is None:
            return v

        from src.core.constants import IMAGE_GENERATION_VALID_SIZES

        if v not in IMAGE_GENERATION_VALID_SIZES:
            raise ValueError(
                f"Invalid image size: {v}. "
                f"Must be one of {', '.join(IMAGE_GENERATION_VALID_SIZES)}"
            )
        return v

    @field_validator("image_generation_output_format", mode="before", check_fields=False)
    @classmethod
    def validate_image_generation_format(cls, v: str | None) -> str | None:
        """Validate image generation output format is supported."""
        if v is None:
            return v

        from src.core.constants import IMAGE_GENERATION_VALID_FORMATS

        if v not in IMAGE_GENERATION_VALID_FORMATS:
            raise ValueError(
                f"Invalid image format: {v}. "
                f"Must be one of {', '.join(IMAGE_GENERATION_VALID_FORMATS)}"
            )
        return v


# ============================================================================
# Password Validation
# ============================================================================


def password_field(description: str = "User password") -> Any:
    """
    Factory for password field with standard constraints.

    Usage:
        password: str = password_field()
        new_password: str = password_field("New password")

    Returns:
        Pydantic Field with min/max length and description
    """
    return Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description=f"{description} ({PASSWORD_MIN_LENGTH}-{PASSWORD_MAX_LENGTH} characters)",
    )


class PasswordValidatorMixin:
    """
    Mixin providing password field validation with security requirements.

    Add to any Pydantic model that has a `password` or `new_password` field.
    Validates against strict password requirements (uppercase, lowercase, digit, special char).
    """

    @field_validator("password", "new_password", mode="before", check_fields=False)
    @classmethod
    def validate_password_field(cls, v: str | None) -> str | None:
        """Validate password meets security requirements."""
        if v is None:
            return v
        return validate_password_strict(v)


class UserBase(BaseModel, TimezoneValidatorMixin, ThemeValidatorMixin, FontFamilyValidatorMixin):
    """
    Base schema for user data - single source of truth for user fields.

    Contains all common user fields found in UserResponse (auth) and UserProfile (users).
    Specific schemas can extend this and add domain-specific fields.

    Note: Does not include `language`, `personality_id`, or `home_address` which are
    specific to UserProfile. Subclasses should add these as needed.
    """

    id: UUID = Field(..., description="User ID")
    email: EmailStr = Field(..., description="User email address")
    full_name: str | None = Field(None, description="User full name")
    timezone: str = Field(default="Europe/Paris", description="User's IANA timezone")
    is_active: bool = Field(..., description="User account is active")
    is_verified: bool = Field(..., description="User email is verified")
    is_superuser: bool = Field(..., description="User has superuser privileges")
    oauth_provider: str | None = Field(None, description="OAuth provider name")
    picture_url: str | None = Field(None, description="Profile picture URL")
    memory_enabled: bool = Field(default=True, description="Long-term memory enabled")
    voice_enabled: bool = Field(default=False, description="Voice comments (TTS) enabled")
    voice_mode_enabled: bool = Field(
        default=False, description="Voice mode (wake word + STT input) enabled"
    )
    tokens_display_enabled: bool = Field(
        default=False, description="Token usage and costs display enabled"
    )
    debug_panel_enabled: bool = Field(
        default=False, description="Debug panel enabled (requires admin user access setting)"
    )
    sub_agents_enabled: bool = Field(default=True, description="Sub-agent delegation enabled")
    onboarding_completed: bool = Field(
        default=False, description="Onboarding tutorial has been completed/dismissed"
    )
    theme: str = Field(default="system", description="User display mode: light, dark, or system")
    color_theme: str = Field(
        default="default", description="User color theme: default, ocean, forest, sunset, slate"
    )
    font_family: str = Field(
        default="system",
        description="User font family: system, noto-sans, plus-jakarta-sans, ibm-plex-sans, geist, source-sans-pro, merriweather, libre-baskerville, fira-code",
    )
    # Image Generation preferences
    image_generation_enabled: bool = Field(default=False, description="AI image generation enabled")
    image_generation_default_quality: str = Field(
        default="medium", description="Default image quality: low, medium, high"
    )
    image_generation_default_size: str = Field(
        default="1024x1024", description="Default image size"
    )
    image_generation_output_format: str = Field(
        default="png", description="Default output format: png, jpeg, webp"
    )

    created_at: datetime = Field(..., description="Account creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {"from_attributes": True}

    @field_validator("memory_enabled", mode="before")
    @classmethod
    def set_memory_enabled_default(cls, v: bool | None) -> bool:
        """Ensure memory_enabled defaults to True if None."""
        return v if v is not None else True

    @field_validator("voice_enabled", mode="before")
    @classmethod
    def set_voice_enabled_default(cls, v: bool | None) -> bool:
        """Ensure voice_enabled defaults to False if None."""
        return v if v is not None else False

    @field_validator("voice_mode_enabled", mode="before")
    @classmethod
    def set_voice_mode_enabled_default(cls, v: bool | None) -> bool:
        """Ensure voice_mode_enabled defaults to False if None."""
        return v if v is not None else False

    @field_validator("tokens_display_enabled", mode="before")
    @classmethod
    def set_tokens_display_enabled_default(cls, v: bool | None) -> bool:
        """Ensure tokens_display_enabled defaults to False if None."""
        return v if v is not None else False

    @field_validator("debug_panel_enabled", mode="before")
    @classmethod
    def set_debug_panel_enabled_default(cls, v: bool | None) -> bool:
        """Ensure debug_panel_enabled defaults to False if None."""
        return v if v is not None else False

    @field_validator("sub_agents_enabled", mode="before")
    @classmethod
    def set_sub_agents_enabled_default(cls, v: bool | None) -> bool:
        """Ensure sub_agents_enabled defaults to True if None (opt-out)."""
        return v if v is not None else True

    @field_validator("onboarding_completed", mode="before")
    @classmethod
    def set_onboarding_completed_default(cls, v: bool | None) -> bool:
        """Ensure onboarding_completed defaults to False if None."""
        return v if v is not None else False

    @field_validator("theme", mode="before")
    @classmethod
    def set_theme_default(cls, v: str | None) -> str:
        """Ensure theme defaults to 'system' if None."""
        return v if v is not None else "system"

    @field_validator("color_theme", mode="before")
    @classmethod
    def set_color_theme_default(cls, v: str | None) -> str:
        """Ensure color_theme defaults to 'default' if None."""
        return v if v is not None else "default"

    @field_validator("font_family", mode="before")
    @classmethod
    def set_font_family_default(cls, v: str | None) -> str:
        """Ensure font_family defaults to 'system' if None."""
        return v if v is not None else "system"
