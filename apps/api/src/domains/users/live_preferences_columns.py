"""The person's live-conversation reflexes — the column of ``users`` they live in.

A declarative mixin like ``PhoneIdentityColumns`` (ADR-299): one nullable
JSONB, read by ``domains/live/preferences.read_live_preferences`` (tolerant),
written by ``PUT /live/preferences`` as a NEW dict (the JSONB rule).
Migration ``d7f2a4c6e8b1``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class LivePreferencesColumns:
    """Mapped column of the live preferences (a declarative mixin)."""

    live_preferences: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        comment=(
            "Live conversation preferences (interruptions, end of speech, result "
            "delivery, the provider the sessions open on)."
        ),
    )


__all__ = ["LivePreferencesColumns"]
