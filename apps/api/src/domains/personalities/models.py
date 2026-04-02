"""
Database models for LLM personality system.

Defines Personality and PersonalityTranslation entities with their relationships.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.config import settings
from src.infrastructure.database.models import BaseModel

if TYPE_CHECKING:
    from src.domains.auth.models import User


class Personality(BaseModel):
    """
    LLM personality configuration.

    Defines the behavior and tone of the LLM assistant through
    prompt instructions. Each personality has localized translations
    for user-facing title and description.

    Attributes:
        code: Unique identifier (e.g., 'enthusiastic', 'professor')
        emoji: Display emoji for the personality
        is_default: Whether this is the default personality for new users
        is_active: Whether the personality is available for selection
        sort_order: Display order in UI (lower = first)
        prompt_instruction: LLM instruction text (injected into {personnalite})
    """

    __tablename__ = "personalities"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    emoji: Mapped[str] = mapped_column(String(10), nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true", index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False, server_default="0")
    prompt_instruction: Mapped[str] = mapped_column(Text, nullable=False)

    # Big Five personality traits (Psyche Engine)
    # Nullable: not all personalities need traits (backward compatibility)
    trait_openness: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Big Five Openness [0, 1]."
    )
    trait_conscientiousness: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Big Five Conscientiousness [0, 1]."
    )
    trait_extraversion: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Big Five Extraversion [0, 1]."
    )
    trait_agreeableness: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Big Five Agreeableness [0, 1]."
    )
    trait_neuroticism: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Big Five Neuroticism [0, 1]."
    )

    # PAD baseline overrides (for caricature personalities where linear mapping fails)
    pad_pleasure_override: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="PAD Pleasure override [-1, +1]. Null = auto-compute."
    )
    pad_arousal_override: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="PAD Arousal override [-1, +1]. Null = auto-compute."
    )
    pad_dominance_override: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="PAD Dominance override [-1, +1]. Null = auto-compute."
    )

    # Relationships
    translations: Mapped[list["PersonalityTranslation"]] = relationship(
        back_populates="personality",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    users: Mapped[list["User"]] = relationship(
        back_populates="personality",
        foreign_keys="User.personality_id",
    )

    def __repr__(self) -> str:
        return f"<Personality(id={self.id}, code={self.code}, emoji={self.emoji})>"

    def get_translation(self, language_code: str) -> "PersonalityTranslation | None":
        """
        Get translation for a specific language with fallback.

        Priority: requested language -> fr -> en -> first available
        """
        # Try exact match
        for t in self.translations:
            if t.language_code == language_code:
                return t

        # Try fallbacks
        fallback_languages = (settings.default_language, "en")
        for fallback in fallback_languages:
            for t in self.translations:
                if t.language_code == fallback:
                    return t

        # Return first available
        return self.translations[0] if self.translations else None


class PersonalityTranslation(BaseModel):
    """
    Localized personality metadata (title and description).

    Each personality can have multiple translations, one per supported language.
    Translations can be manually created or auto-translated via GPT-4.1-nano.

    Attributes:
        personality_id: FK to parent personality
        language_code: ISO language code (fr, en, es, de, it, zh-CN)
        title: Localized personality name
        description: Localized personality description
        is_auto_translated: Whether this was created by automatic translation
    """

    __tablename__ = "personality_translations"

    personality_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("personalities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    language_code: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_auto_translated: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="false"
    )

    # Relationships
    personality: Mapped["Personality"] = relationship(back_populates="translations")

    __table_args__ = (
        UniqueConstraint("personality_id", "language_code", name="uq_personality_translation_lang"),
    )

    def __repr__(self) -> str:
        return (
            f"<PersonalityTranslation(id={self.id}, lang={self.language_code}, title={self.title})>"
        )
