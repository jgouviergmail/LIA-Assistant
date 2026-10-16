"""The voices LIA speaks with for one person — the column of ``users`` they live in.

A declarative mixin like ``LivePreferencesColumns``: one nullable JSONB, kept PER
VOICE PROVIDER (the voice slot's provider: every model of it offers the same
voices) so a model switched for another keeps the choice and a provider switched
back to finds the voices chosen on it. Read forgivingly and written as a NEW
mapping by ``domains/voice/lia_voices`` (ADR-345 amendments 2026-10-14 and
2026-10-16). Migrations ``4c2e8a6f1d3b`` (the column) and ``1ed6c591761a`` (its
comment, once the key became the provider).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

#: The column comment, shared with the migration — the replay check compares them.
LIA_VOICES_COMMENT = (
    "The voices LIA speaks with in the chat for this account, per voice provider: "
    "{provider: {male, female}} (an entry keyed provider/model by an older release is "
    "read until the next save). A gender left out speaks with the instance's voice."
)


class VoicePreferencesColumns:
    """Mapped column of LIA's voices (a declarative mixin)."""

    # ``none_as_null``: a Python None is SQL NULL, never the JSON ``null`` — the
    # forgetting of a person's last voice and the account deletion write None,
    # and on a JSON null the atomic merge builds an array (and a removal fails).
    lia_voices: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=True),
        nullable=True,
        default=None,
        comment=LIA_VOICES_COMMENT,
    )


__all__ = ["LIA_VOICES_COMMENT", "VoicePreferencesColumns"]
