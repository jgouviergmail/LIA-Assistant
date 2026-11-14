"""The writing-style profile of one account (ADR-383).

One row per account: what a model wrote about HOW the person writes their e-mails —
greeting, sign-off, signature, register, length, tone — from their latest sent
e-mails, never WHAT they wrote about. The profile rests encrypted; the row also says
how many e-mails it was learned from and when. A row whose profile is NULL was BUILT
and taught nothing (too few sent e-mails): it is not read again before it is due,
which is the question « has this been built? » asked honestly (ADR-248).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class WritingStyle(BaseModel):
    """How one account writes its e-mails, as the drafters read it."""

    __tablename__ = "writing_styles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    profile_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="The style profile, encrypted at rest; NULL = the sent mail taught no style.",
    )
    mails_read: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="How many sent e-mails the profile was learned from.",
    )
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the profile was learned (UTC); it is learned again once too old.",
    )


__all__ = ["WritingStyle"]
