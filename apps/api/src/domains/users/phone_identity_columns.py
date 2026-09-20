"""The person's own phone identity — the columns of ``users`` it lives in.

Extracted from ``users/models.py`` (lot 8 of the phone-as-a-channel
programme) as one cohesive mixin: the number the person declared, when LIA
heard them answer it, and the switches of their own calls. ``User``
inherits it; nothing else does. The migrations that created these columns are
``f1a6c8e4d2b3`` (number, verification, rich context), ``c4d9f1a3e5b7``
(disabled domains) and ``c9e2a4b6d8f1`` (call mode, ADR-301).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text
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
    # ADR-301: how the person's own calls run, in the voice sessions' mode
    # vocabulary (``voice_sessions/session.VoiceSessionMode``): ``delegated``
    # — Live, the voice hands every request to the chat — or ``direct`` —
    # Live direct, the voice reads LIA's tools itself and the call is relayed
    # at its end. Live is the default (owner decision 2026-09-20).
    phone_call_mode: Mapped[str] = mapped_column(
        String(16),
        default="delegated",
        nullable=False,
        server_default="delegated",
        comment="How the person's own calls run: delegated (Live) or direct (Live direct).",
    )


__all__ = ["PhoneIdentityColumns"]
