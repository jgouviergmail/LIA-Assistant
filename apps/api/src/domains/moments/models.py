"""Anticipated moments — LIA comes back at an INSTANT, not at a tick.

The heartbeat answers a clock: a scheduler fires every thirty minutes, draws a
random batch of accounts and asks a model whether anything is worth saying. That
shape cannot serve « your meeting ended fifteen minutes ago » — by the time the
tick falls the moment has passed, and the calendar window it reads starts at
``now`` and looks FORWARD, so a finished event is invisible to it by
construction.

A moment row says: *at this instant there will be something to say to this
person about this thing*. It is detected ahead of time, claimed by exactly one
worker when it falls due, and settled from an explicit result.

**This is not a register.** Settled rows are purged after
``moments_retention_days``; the durable trace of what LIA actually did lives in
``agent_effects`` and ``heartbeat_notifications``, which outlive it.

Two shapes are deliberate:

- ``kind`` and ``state`` are ``String`` columns with Python enums for the
  vocabulary, exactly like ``workboard_tickets`` and ``open_loops``. A native
  enum invites the trap ADR-276 measured: a bare enum member as the RESULT of a
  SQL expression binds as ``NullType`` and sends its VALUE where the column
  stores its NAME.
- ``payload`` carries what is needed to DEDUPLICATE and SCORE, never what is
  needed to write the sentence. The claim revalidates the fact against its
  source anyway, so storing the people involved would be personal data kept for
  nothing.

See ``docs/superpowers/specs/2026-09-11-anticipated-moments-design.md``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class MomentKind(str, Enum):
    """What kind of instant this row anticipates.

    One member in lot 1. The registry (``moments/kinds.py``) is what makes the
    next ones additive: a kind is a detector, a due rule, a prompt section and a
    label, declared together and checked at boot.
    """

    EVENT_FOLLOWUP = "event_followup"


class MomentState(str, Enum):
    """Where a row is in its one-way life.

    ``pending`` to ``claimed`` to one of the four settled states. Every path out
    of ``claimed`` writes a settled state explicitly: absence of an exception is
    never read as delivery (ADR-263).
    """

    PENDING = "pending"
    CLAIMED = "claimed"
    SERVED = "served"
    SKIPPED = "skipped"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class MomentSkipReason(str, Enum):
    """Why a claimed moment was not served, on a bounded vocabulary.

    Bounded because it is counted: an operator reads
    ``proactive_moments_total{outcome}`` to tell « the feature is quiet because
    nothing happened » from « the feature is quiet because every account is at
    its daily ceiling ». A free-text reason answers neither.
    """

    NOT_ELIGIBLE = "not_eligible"
    LLM_SKIP = "llm_skip"
    QUOTA = "quota"
    CANCELLED = "cancelled"
    REVALIDATION_FAILED = "revalidation_failed"
    DISPATCH_FAILED = "dispatch_failed"


class ProactiveMoment(BaseModel):
    """One anticipated instant, owned by one account.

    Attributes:
        user_id: Whose moment. Also the clause that stops a claim from anywhere
            else touching somebody else's row.
        kind: A ``MomentKind`` value.
        source_ref: What the moment is ABOUT, in the source's own vocabulary
            (a provider event id, ``ticket:{uuid}``, ...). With ``user_id`` and
            ``kind`` it forms the identity the detector cannot file twice.
        due_at: When there will be something to say.
        not_after: When there no longer will be. A moment that misses its window
            expires rather than arriving late: « how did yesterday evening go »
            is not a moment.
        state: A ``MomentState`` value.
        claim_owner: The token of the worker holding the row. Every settle is
            conditioned on it, so a zombie's late write lands on nothing.
        claimed_at: When the claim was taken (also what a stale-claim sweep
            would read).
        settled_at: When the row reached a settled state.
        skip_reason: A ``MomentSkipReason`` value when ``state`` is ``skipped``.
        payload: What deduplication and scoring need, and nothing else.
    """

    __tablename__ = "proactive_moments"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="MomentKind value — String, never a native enum (NullType trap).",
    )
    source_ref: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="What the moment is about, in the source's own vocabulary.",
    )
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When there will be something to say (UTC).",
    )
    not_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When there no longer will be — the row expires instead of arriving late.",
    )
    state: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=MomentState.PENDING.value,
        server_default=text(f"'{MomentState.PENDING.value}'"),
        comment="MomentState value.",
    )
    claim_owner: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Owner token of the worker holding this row; every settle quotes it.",
    )
    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    skip_reason: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="MomentSkipReason value when the state is 'skipped'.",
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
        comment="Deduplication and scoring only — never the people involved.",
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "kind",
            "source_ref",
            name="uq_proactive_moments_identity",
        ),
        # The sweep scans pending rows and nothing else; within a day the
        # settled rows outnumber them by orders of magnitude.
        Index(
            "ix_proactive_moments_due_pending",
            "due_at",
            postgresql_where=text(f"state = '{MomentState.PENDING.value}'"),
        ),
    )
