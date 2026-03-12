"""
Pydantic schemas for personality API validation.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.domains.personalities.constants import (
    DEFAULT_LANGUAGE,
    MAX_CODE_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_EMOJI_LENGTH,
    MAX_PROMPT_LENGTH,
    MAX_TITLE_LENGTH,
    PERSONALITY_CODE_PATTERN,
    SUPPORTED_LANGUAGES,
)

# =============================================================================
# Translation Schemas
# =============================================================================


class PersonalityTranslationCreate(BaseModel):
    """Schema for creating a personality translation."""

    language_code: str = Field(..., max_length=10)
    title: str = Field(..., min_length=1, max_length=MAX_TITLE_LENGTH)
    description: str = Field(..., min_length=1, max_length=MAX_DESCRIPTION_LENGTH)

    @field_validator("language_code")
    @classmethod
    def validate_language_code(cls, v: str) -> str:
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {v}. Supported: {SUPPORTED_LANGUAGES}")
        return v


class PersonalityTranslationUpdate(BaseModel):
    """Schema for updating a personality translation."""

    title: str | None = Field(None, min_length=1, max_length=MAX_TITLE_LENGTH)
    description: str | None = Field(None, min_length=1, max_length=MAX_DESCRIPTION_LENGTH)


class PersonalityTranslationResponse(BaseModel):
    """Schema for translation response."""

    id: UUID
    language_code: str
    title: str
    description: str
    is_auto_translated: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# =============================================================================
# Personality Schemas
# =============================================================================


class PersonalityCreate(BaseModel):
    """
    Schema for creating a personality.

    Supports two formats:
    1. Simplified (from frontend): title, description, source_language
    2. Full: translations list with PersonalityTranslationCreate objects
    """

    code: str = Field(
        ...,
        min_length=2,
        max_length=MAX_CODE_LENGTH,
        pattern=PERSONALITY_CODE_PATTERN,
        description="Unique identifier (lowercase, alphanumeric with underscores)",
    )
    emoji: str = Field(..., min_length=1, max_length=MAX_EMOJI_LENGTH)
    is_active: bool = Field(True, description="Whether personality is available")
    is_default: bool = Field(False, description="Make this the default personality")
    sort_order: int = Field(0, ge=0, description="Display order (lower = first)")
    prompt_instruction: str = Field(
        ...,
        min_length=10,
        max_length=MAX_PROMPT_LENGTH,
        description="LLM instruction text",
    )
    # Simplified format (from frontend)
    title: str | None = Field(None, min_length=1, max_length=MAX_TITLE_LENGTH)
    description: str | None = Field(None, min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    source_language: str = Field(DEFAULT_LANGUAGE, description="Language for title/description")
    # Full format (translations list)
    translations: list[PersonalityTranslationCreate] | None = Field(
        None, description="Optional translations list"
    )

    def get_translations(self) -> list[PersonalityTranslationCreate]:
        """Get translations list, converting from simplified format if needed."""
        if self.translations:
            return self.translations
        if self.title and self.description:
            return [
                PersonalityTranslationCreate(
                    language_code=self.source_language,
                    title=self.title,
                    description=self.description,
                )
            ]
        raise ValueError("Either 'translations' or both 'title' and 'description' required")


class PersonalityUpdate(BaseModel):
    """Schema for updating a personality."""

    # Core fields
    emoji: str | None = Field(None, min_length=1, max_length=MAX_EMOJI_LENGTH)
    is_active: bool | None = None
    is_default: bool | None = None
    sort_order: int | None = Field(None, ge=0)
    prompt_instruction: str | None = Field(None, min_length=10, max_length=MAX_PROMPT_LENGTH)

    # Code modification (with uniqueness check in service)
    code: str | None = Field(
        None,
        min_length=2,
        max_length=MAX_CODE_LENGTH,
        description="Unique identifier (lowercase, alphanumeric with underscores)",
    )

    # Translation modification (triggers propagation if changed)
    title: str | None = Field(None, min_length=1, max_length=MAX_TITLE_LENGTH)
    description: str | None = Field(None, min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    source_language: str | None = Field(
        None,
        description="Language code for title/description (fr, en, es, de, it, zh-CN)",
    )

    @field_validator("code")
    @classmethod
    def validate_code_pattern(cls, v: str | None) -> str | None:
        """Validate code follows pattern if provided."""
        import re

        if v is not None and not re.match(PERSONALITY_CODE_PATTERN, v):
            raise ValueError(
                f"Code must match pattern: {PERSONALITY_CODE_PATTERN} "
                "(lowercase, starts with letter, alphanumeric with underscores)"
            )
        return v

    @field_validator("source_language")
    @classmethod
    def validate_source_language(cls, v: str | None) -> str | None:
        """Validate source_language is supported."""
        if v is not None and v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"Unsupported language: {v}. Supported: {SUPPORTED_LANGUAGES}")
        return v


class PersonalityResponse(BaseModel):
    """Full personality response with all translations (admin)."""

    id: UUID
    code: str
    emoji: str
    is_default: bool
    is_active: bool
    sort_order: int
    prompt_instruction: str
    translations: list[PersonalityTranslationResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PersonalityListItem(BaseModel):
    """
    Simplified personality for user-facing list (localized).

    Contains only the fields needed for display, with title/description
    already localized to the user's language.
    """

    id: UUID
    code: str
    emoji: str
    is_default: bool
    title: str  # Localized to user's language
    description: str  # Localized to user's language

    model_config = {"from_attributes": True}


class PersonalityListResponse(BaseModel):
    """Paginated list of personalities for users."""

    personalities: list[PersonalityListItem]
    total: int


# =============================================================================
# User Preference Schemas
# =============================================================================


class UserPersonalityUpdate(BaseModel):
    """Schema for updating user's personality preference."""

    personality_id: UUID | None = Field(None, description="Personality ID or NULL to use default")


class UserPersonalityResponse(BaseModel):
    """Schema for user's current personality."""

    personality_id: UUID | None
    personality: PersonalityListItem | None
