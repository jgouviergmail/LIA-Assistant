"""Workboard models (ADR-276).

One row per ticket, shared by its owner and its assignee (D7/D8): the board of
user U is « owner = U or assignee = U ». Comments and an append-only event log
hang off a ticket and die with it.

Three shapes are load-bearing and are asserted by ``test_models.py``:

- **A NULL assignee means « the owner holds it », and the FK is SET NULL.**
  Four paths hard-delete a ``users`` row and only one of them runs the account
  purge (the demo purge; the unverified-account cleanup, the admin hard delete
  and the GDPR delete do not). CASCADE would destroy the OWNER's ticket when
  their peer leaves; RESTRICT would block the three paths that never release.
  SET NULL hands the ticket back to its owner on every path there is and every
  path there will be. The purge still releases EXPLICITLY, because account
  deletion SCRUBS the users row rather than deleting it, so no FK action fires
  there — two mechanisms, each covering what the other cannot.
- **There is no ``peer_connection_id`` column.** An earlier draft stored the
  connection that authorised a peer assignment, with a CHECK tying the two
  columns together. Measured 2026-09-09 on a real PostgreSQL server: deleting the peer's
  account fires TWO independent foreign-key actions on this row (assignee to
  NULL, connection to NULL) and the CHECK rejects whichever intermediate state
  comes first — and no cascade ORDER is guaranteed, so every cross-column CHECK
  here is violable. ``CHECK`` constraints cannot be ``DEFERRABLE`` in
  PostgreSQL, so the column had to go rather than the invariant. Nothing is
  lost: ``peer_connections`` holds ONE row per pair for life (re-requests are
  status transitions), so the pair ``(owner, assignee)`` IS the connection, and
  the service resolves it at every write anyway — D8's rule that a share is
  re-checked at execution time, never trusted from a stored row.
- **The event log carries no ``updated_at``.** A ledger row is never updated
  (the ``peer_access_log`` precedent).

Status columns are ``String(20)`` + lowercase ``str``-Enum values (the
``open_loops`` / ``peers`` pattern), never ``Enum(native_enum=False)``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import OUT_OF_TURN_EXECUTION_MODE_DEFAULT
from src.domains.workboard.constants import (
    STATUS_ORDER,
    ActorKind,
    AssigneeKind,
    RunOutcome,
    TicketPriority,
    TicketStatus,
)
from src.infrastructure.database.models import BaseModel, UUIDMixin
from src.infrastructure.database.session import Base

#: What the psql prompt tells a DBA the two vocabulary columns hold.
#: DERIVED, because a comment is documentation the database itself carries and
#: a hand-written copy drifts in silence: it still listed ``cancelled`` — gone
#: at lot 8 — and had never learnt ``confirming``, added at lot 7. Deriving it
#: makes the next change a drift the migration check asks about.
_STATUS_VOCABULARY: str = " | ".join(STATUS_ORDER)
_OUTCOME_VOCABULARY: str = " | ".join(outcome.value for outcome in RunOutcome)


class WorkboardTicket(BaseModel):
    """A unit of work with a lifecycle, an assignee and a result."""

    __tablename__ = "workboard_tickets"

    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The board it was created on. Dies with the account.",
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workboard_tickets.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Parent ticket (ONE level — a child never has children).",
    )
    title: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="What the ticket is.",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="The brief LIA runs when assigned; the owner's words.",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=TicketStatus.TODO.value,
        comment=_STATUS_VOCABULARY,
    )
    priority: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=TicketPriority.MEDIUM.value,
        comment="low | medium | high | urgent",
    )
    start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC instant work may start.",
    )
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC instant it is due.",
    )
    assignee_kind: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=AssigneeKind.HUMAN.value,
        comment="human | lia — whose hands, or whose assistant.",
    )
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Account holding it; NULL means the owner does. SET NULL releases it.",
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Order inside a column, on the OWNER's board.",
    )
    follow_owner: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="Owner wants chat notifications about this ticket.",
    )
    follow_assignee: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="Assignee wants chat notifications; reset on reassignment.",
    )
    created_by: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=ActorKind.USER.value,
        comment="user | lia | peer — who created it.",
    )
    status_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When status last changed (closed-hide filter, waiting-too-long nudge).",
    )
    execution_mode: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=OUT_OF_TURN_EXECUTION_MODE_DEFAULT,
        server_default=OUT_OF_TURN_EXECUTION_MODE_DEFAULT,
        comment=(
            "pipeline | react — how LIA runs THIS ticket. The person may change "
            "it at any point of the ticket's life; the next run reads it."
        ),
    )
    run_not_before: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Quota back-off; set by the sweep only.",
    )
    run_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="A run holds this ticket since.",
    )
    run_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Attempts of the CURRENT run.",
    )
    run_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Runs in the ticket's life (bounds the hidden transcripts).",
    )
    last_run_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="run_id of the last run (registers join key).",
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC instant the last run ended.",
    )
    last_run_outcome: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment=_OUTCOME_VOCABULARY,
    )
    last_run_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Typed code + bounded message; never a traceback.",
    )
    last_run_tokens_in: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Prompt tokens the last run spent.",
    )
    last_run_tokens_out: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Completion tokens the last run spent.",
    )
    last_run_cost_eur: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 6),
        nullable=True,
        comment="Cost of the last run, snapshotted from token_usage_logs.",
    )
    total_tokens_in: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Prompt tokens every run of this ticket has spent.",
    )
    total_tokens_out: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Completion tokens every run has produced.",
    )
    total_tokens_cache: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Cached prompt tokens every run has read.",
    )
    total_google_requests: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="Google API requests every run has made.",
    )
    total_cost_eur: Mapped[Decimal] = mapped_column(
        Numeric(12, 6),
        nullable=False,
        default=Decimal("0"),
        server_default="0",
        comment="What this ticket has cost since it was created, run by run.",
    )
    last_nudged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last heartbeat notification that surfaced this ticket (cooldown).",
    )
    nudge_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="How many notifications surfaced this ticket.",
    )
    pending_action: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "The draft the person must confirm on the ticket (lot 7): draft_id, "
            "draft_type, draft_content, tool_name, question, approved."
        ),
    )

    # NOTE: no ORM relationship to User — the two FKs + the purge handle
    # deletion, and an unused relationship creates mapper import-order
    # landmines (same decision as OpenLoop and UserMCPServer).

    __table_args__ = (
        Index("ix_workboard_tickets_owner_status", "owner_user_id", "status"),
        Index("ix_workboard_tickets_assignee_status", "assignee_user_id", "status"),
        # The sweep's eligibility scan (lot 2). Partial: the vast majority of a
        # board is not waiting for LIA, and the index should not carry it.
        Index(
            "ix_workboard_tickets_lia_todo",
            "start_at",
            postgresql_where=text(
                "assignee_kind = 'lia' AND status = 'todo' AND run_claimed_at IS NULL"
            ),
        ),
    )

    @property
    def effective_assignee_id(self) -> uuid.UUID:
        """The account that actually holds this ticket.

        ``assignee_user_id`` is NULL when the owner holds it — the shape that
        makes a departing peer release the ticket automatically. Every reader
        goes through this property rather than repeating the convention, so
        « who holds it » has one implementation.

        Returns:
            The assignee's id, or the owner's when nobody else holds it.
        """
        return self.assignee_user_id or self.owner_user_id

    def __repr__(self) -> str:
        return (
            f"<WorkboardTicket(id={self.id}, status={self.status}, "
            f"assignee_kind={self.assignee_kind})>"
        )


class WorkboardComment(BaseModel):
    """One comment on a ticket, by a person or by LIA (a run's answer)."""

    __tablename__ = "workboard_comments"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workboard_tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The ticket this comment belongs to.",
    )
    author_kind: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="user | lia | peer",
    )
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Who wrote it; NULL once that account is gone.",
    )
    body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Plain text.",
    )
    run_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="The run that wrote it, when LIA did.",
    )

    def __repr__(self) -> str:
        return f"<WorkboardComment(id={self.id}, author_kind={self.author_kind})>"


class WorkboardTicketEvent(Base, UUIDMixin):
    """Append-only history of a ticket: what people did, and when a run ran.

    Immutable (``created_at`` only, the ``peer_access_log`` pattern): rows are
    never updated, so ``TimestampMixin`` would carry a column that lies.
    """

    __tablename__ = "workboard_ticket_events"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workboard_tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="The ticket this event belongs to.",
    )
    actor_kind: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="user | lia | peer",
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="Who acted; NULL once that account is gone.",
    )
    kind: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="created | status_changed | assigned | priority_changed | dates_changed "
        "| run_started | run_finished | follow_changed",
    )
    payload: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Bounded {from, to} facts; never free text.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        comment="When it happened (UTC).",
    )

    def __repr__(self) -> str:
        return f"<WorkboardTicketEvent(id={self.id}, kind={self.kind})>"
