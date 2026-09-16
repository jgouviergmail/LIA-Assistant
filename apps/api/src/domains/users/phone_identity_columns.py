"""The person's own phone identity — the columns of ``users`` it lives in.

Extracted from ``users/models.py`` (lot 8 of the phone-as-a-channel
programme) as one cohesive mixin: the number the person declared, when LIA
heard them answer it, and the two switches of their own calls. ``User``
inherits it; nothing else does. The migrations that created these columns are
``f1a6c8e4d2b3`` (number, verification, rich context) and ``c4d9f1a3e5b7``
(disabled domains).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column


class PhoneIdentityColumns:
    """Mapped columns of the person's phone identity (a declarative mixin)."""

    # The person's own phone number (lot 1 of the phone-as-a-channel programme):
    # declared in the settings, stored encrypted like the home address, and
    # VERIFIED by a call that reads a code aloud. Only a verified number may be
    # dialled as « you » without a confirmation card.
    phone_number_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Fernet-encrypted E.164 phone number the person declared as their own.",
    )
    phone_number_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When LIA heard the person answer the declared number; NULL = unverified.",
    )
    phone_rich_context_enabled: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        server_default="true",
        comment="Whether an owner call carries the chat's context beyond free/busy.",
    )
    # Lot 8: the phone domains the person switched OFF for their own calls
    # (the DISABLED set, so a domain the phone starts offering later is on by
    # default). Vocabulary: ``domains/shared/phone_domains.PHONE_DOMAINS``.
    phone_disabled_domains: Mapped[list[str]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
        server_default="[]",
        comment="Phone domains switched off for owner calls (the disabled set).",
    )


__all__ = ["PhoneIdentityColumns"]
