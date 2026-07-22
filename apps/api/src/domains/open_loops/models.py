"""Open Loops domain models.

An OpenLoop is a tracked commitment extracted from conversation (P5,
ADR-139): either something the user owes a counterparty (``user_owes``)
or something the user is waiting on (``waiting_on_other``). Loops are
closed conversationally (the extractor detects "c'est fait"), via the
API, or soft-expired after ``open_loops_expiry_days`` of inactivity
(lazy expiry in the heartbeat fetcher — no dedicated scheduler job).
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class OpenLoopDirection(str, Enum):
    """Who owes whom in the tracked commitment."""

    USER_OWES = "user_owes"  # The user committed to do something
    WAITING_ON_OTHER = "waiting_on_other"  # The user is waiting on someone


class OpenLoopStatus(str, Enum):
    """Lifecycle of an open loop."""

    OPEN = "open"  # Being tracked (nudge-eligible)
    CLOSED = "closed"  # Resolved (conversationally, via API)
    EXPIRED = "expired"  # Soft-expired after prolonged inactivity


class OpenLoopSourceKind(str, Enum):
    """Where the loop was extracted from (v1: conversation only)."""

    CONVERSATION = "conversation"


class OpenLoop(BaseModel):
    """A tracked commitment (open loop) owned by a user.

    ``due_hint`` is a best-effort UTC datetime parsed from the conversation
    ("d'ici vendredi") — advisory for nudge timing, never authoritative.
    ``last_nudged_at``/``nudge_count`` implement the anti-nag cooldown:
    the heartbeat fetcher only surfaces loops outside the cooldown, and
    ``proactive_task`` bumps them after a notification actually used the
    OPEN_LOOPS source.
    """

    __tablename__ = "open_loops"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    subject: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="What the commitment is about, in the user's language.",
    )

    counterparty: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Person or organization on the other side of the loop.",
    )

    direction: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="user_owes | waiting_on_other (OpenLoopDirection).",
    )

    due_hint: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Best-effort deadline parsed from conversation (UTC, advisory).",
    )

    source_kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=OpenLoopSourceKind.CONVERSATION.value,
        comment="Extraction origin (v1: conversation).",
    )

    source_ref: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Conversation thread id the loop was extracted from.",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=OpenLoopStatus.OPEN.value,
        comment="open | closed | expired (OpenLoopStatus).",
    )

    closed_reason: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
        comment="conversational | api | expired — why the loop left OPEN.",
    )

    last_nudged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last heartbeat notification that surfaced this loop (cooldown).",
    )

    nudge_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="How many notifications surfaced this loop.",
    )

    # NOTE: no ORM relationship to User — user_id FK + CASCADE handles
    # deletion, and an unused relationship creates mapper import-order
    # landmines (same decision as UserMCPServer, see users/models.py).

    def __repr__(self) -> str:
        return (
            f"<OpenLoop(id={self.id}, status={self.status}, "
            f"direction={self.direction}, subject={self.subject[:30]!r})>"
        )


# Partial index on the hot path: the heartbeat fetcher and the extractor's
# dedup context both list a user's OPEN loops. Declared post-class so the
# WHERE clause can reference the mapped columns; mirrored in the Alembic
# migration (single head).
Index(
    "ix_open_loops_user_open",
    OpenLoop.user_id,
    postgresql_where=(OpenLoop.status == OpenLoopStatus.OPEN.value),
)
