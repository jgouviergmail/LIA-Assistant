"""How the person wants their generated documents made — the columns of ``users``.

A declarative mixin like ``ImageGenerationColumns``: the illustrations choice and
the animations choice (``core/document_preferences.py`` says what each value
means). Both are read by the document tool at every generation and written
through the generic profile update. Their server defaults are the owner's
defaults, so every sign-up door — and every account created before them —
starts with them. Migration ``d6a3f0c2b8e1``.
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.document_preferences import (
    DOCUMENT_ANIMATIONS_DEFAULT,
    DOCUMENT_ILLUSTRATIONS_DEFAULT,
)


class DocumentPreferencesColumns:
    """Mapped columns of the document preferences (a declarative mixin)."""

    document_illustrations: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DOCUMENT_ILLUSTRATIONS_DEFAULT.value,
        server_default=DOCUMENT_ILLUSTRATIONS_DEFAULT.value,
        comment="Illustrations in generated documents: auto, on_request, never.",
    )
    document_animations: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DOCUMENT_ANIMATIONS_DEFAULT.value,
        server_default=DOCUMENT_ANIMATIONS_DEFAULT.value,
        comment="Animations in generated decks: presented, always, never.",
    )


__all__ = ["DocumentPreferencesColumns"]
