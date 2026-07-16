"""PhoneCall ORM model — one row per placed call (created at draft execution)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Numeric, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class PhoneCallStatus(str, enum.Enum):
    """Lifecycle of an outbound call (distinct from the pre-call PHONE_CALL draft)."""

    DIALING = "dialing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PhoneCallOutcome(str, enum.Enum):
    """Semantic outcome of a completed call, set by the return synthesis."""

    OBJECTIVE_MET = "objective_met"
    PARTIAL = "partial"
    DECLINED = "declined"
    UNREACHABLE = "unreachable"


class NotificationStatus(str, enum.Enum):
    """Durable delivery state of a completed call's return notification (T1).

    A transactional-outbox marker: ``PENDING`` is written ATOMICALLY with the
    call's terminal transition (so a hard crash before the notification is
    dispatched cannot lose it), then flipped to ``DELIVERED`` only after the
    dispatcher succeeds, or ``FAILED`` once bounded retries are exhausted. The
    notification reaper recovers ``PENDING`` rows on restart / on interval.
    """

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class ReturnSynthesisStatus(str, enum.Enum):
    """Durable state of the PRE-synthesis return inbox (T1, approach A).

    The post-call webhook carries the transcript needed to synthesize the return.
    Currently the synthesis runs fire-and-forget, so a crash between the 200 and
    ``mark_completed`` loses the return (the vendor delivers the webhook once).
    This inbox closes that window: on webhook receipt we persist ``RECEIVED`` with
    the ENCRYPTED payload BEFORE responding 200, the return reaper re-runs
    synthesis for ``RECEIVED`` rows a crash left stranded, and ``mark_completed``
    flips it to ``SYNTHESIZED`` while PURGING the encrypted payload (the transcript
    only lives on disk, encrypted, for the brief synthesis window — D-8). A row
    stuck past the max-age cutoff retires to ``FAILED``.
    """

    RECEIVED = "received"
    SYNTHESIZED = "synthesized"
    FAILED = "failed"


# Predicate for the "active call" partial unique index (F12).
# NOTE: SQLAlchemy Enum(native_enum=False) stores the member NAME ('DIALING'),
# not the value ('dialing') — matching the whole codebase (connector_type stores
# 'GOOGLE_GMAIL', status stores 'ACTIVE'). The raw-SQL predicate MUST use the
# uppercase member names, else it matches no rows and the guard silently no-ops.
# The telephony integration test locks this name/value trap.
_ACTIVE_STATUSES_SQL = "status IN ('DIALING', 'IN_PROGRESS')"


class PhoneCall(BaseModel):
    """A single outbound call. PII (``callee_phone``) is encrypted by the service.

    Vendor call costs are the user's own (D-9) — ``call_seconds`` is factual
    metadata, never converted to money. The raw transcript is never stored (D-8):
    only ``summary`` + minimal ``structured_data`` survive, purged after
    ``expires_at`` by the retention reaper.
    """

    __tablename__ = "phone_calls"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    callee_display: Mapped[str] = mapped_column(Text, nullable=False)
    callee_phone: Mapped[str] = mapped_column(Text, nullable=False)  # encrypted by the service
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    objective_window_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    objective_window_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[PhoneCallStatus] = mapped_column(
        Enum(PhoneCallStatus, native_enum=False, length=20),
        nullable=False,
        default=PhoneCallStatus.DIALING,
        index=True,
    )
    elevenlabs_conversation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    call_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    outcome: Mapped[PhoneCallOutcome | None] = mapped_column(
        Enum(PhoneCallOutcome, native_enum=False, length=20), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    initiated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Return-notification durability (T1). NULL until the call reaches a terminal
    # state with a return to deliver; the payload holds the minimal content needed
    # to (re)dispatch without re-synthesizing (LLM cost + non-determinism).
    notification_status: Mapped[NotificationStatus | None] = mapped_column(
        Enum(NotificationStatus, native_enum=False, length=20), nullable=True
    )
    notification_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    notification_attempts: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default=text("0")
    )
    # Pre-synthesis return inbox (T1 approach A). NULL until the post-call webhook
    # is received; ``return_webhook_encrypted`` holds the Fernet-encrypted raw
    # payload (transcript) needed to (re)synthesize after a crash, PURGED to NULL
    # by ``mark_completed`` once synthesis succeeds so the transcript never rests
    # at rest beyond the synthesis window (D-8).
    return_status: Mapped[ReturnSynthesisStatus | None] = mapped_column(
        Enum(ReturnSynthesisStatus, native_enum=False, length=20), nullable=True
    )
    return_webhook_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    return_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        # F12: at most one active (dialing/in_progress) call per user, enforced
        # atomically at the DB level (never SELECT-then-check).
        Index(
            "uq_phone_calls_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text(_ACTIVE_STATUSES_SQL),
        ),
        # Reconciliation fallback key; NULL until initiated, unique among non-null.
        Index(
            "uq_phone_calls_el_conversation",
            "elevenlabs_conversation_id",
            unique=True,
            postgresql_where=text("elevenlabs_conversation_id IS NOT NULL"),
        ),
        # T1: the notification reaper scans only PENDING rows by completion time.
        # native_enum=False stores the member NAME, so the predicate matches 'PENDING'
        # (uppercase) — the same name/value trap as the active-call index above.
        Index(
            "ix_phone_calls_notification_pending",
            "completed_at",
            postgresql_where=text("notification_status = 'PENDING'"),
        ),
        # T1 approach A: the return reaper scans only RECEIVED inbox rows by receipt
        # time (same uppercase-name trap: native_enum=False stores 'RECEIVED').
        Index(
            "ix_phone_calls_return_received",
            "return_received_at",
            postgresql_where=text("return_status = 'RECEIVED'"),
        ),
    )

    def __repr__(self) -> str:
        return f"<PhoneCall(id={self.id}, user_id={self.user_id}, status={self.status})>"
