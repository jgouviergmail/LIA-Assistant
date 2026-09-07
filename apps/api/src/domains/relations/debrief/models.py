"""The relationship debrief — one LLM-written synthesis per person, per day.

One row per ``(user, identity)``: the CURRENT debrief, never a history. A
history would grow without bound for an artefact whose only value is being the
latest one, and the account already owns every source it was written from.

Two things make the row a CLAIM as well as a payload:

- ``state`` says whether a build is in flight, settled, failed or found nothing
  to say. A build is claimed with an atomic conditional UPSERT, so two tabs (or
  a tab and a chat turn) can never spend two LLM calls on the same person;
- ``claim_owner`` + ``held_until`` are the lease. ``held_until`` carries two
  meanings on purpose, and both read the same way — *this row is not available
  before this instant*: for ``building`` it is the lease a crashed builder
  leaves behind, for ``failed`` it is the cooldown before a retry. One column,
  one predicate, no second state machine.

``generated_for`` is the user's LOCAL date, never UTC: "once a day" is a
promise about the reader's day, and a UTC boundary would rebuild at 2 a.m. for
half of Europe (datetime doctrine — the display timezone comes from the user).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel


class DebriefState(str, Enum):
    """Where one debrief stands.

    ``EMPTY`` is not a failure and not a result: the relationship carried
    nothing to synthesise, so no LLM was called and no paragraph was invented.
    Saying "there is nothing yet" is the honest answer; a generic sentence
    written from no evidence would be the dishonest one.
    """

    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"
    EMPTY = "empty"


class RelationDebrief(BaseModel):
    """The current debrief of one relationship, and the claim that produced it."""

    __tablename__ = "relation_debriefs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Owner of the debrief. Dies with the account.",
    )
    name_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Canonical folded identity (IdentityResolver), merges applied.",
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Spelling the debrief was written about.",
    )
    generated_for: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        comment="The user's LOCAL date this debrief belongs to (once a day).",
    )
    generated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC instant the BODY was produced; preserved by a no-change rebuild.",
    )
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Backend-canonical language it was written in (zh-CN, never zh).",
    )
    scope_digest: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Digest of the 360° scope it was written under; a change rebuilds.",
    )
    evidence_digest: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="Digest of the evidence fed to the model; compared only at rebuild.",
    )
    sections_used: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Sections the debrief actually read — the honesty contract.",
    )
    unavailable: Mapped[list[Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment="Sections asked for that could not be read.",
    )
    body: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Versioned structured payload; NULL until a build settles.",
    )
    usage: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="What the call that wrote the body cost (display summary, not an account).",
    )
    state: Mapped[DebriefState] = mapped_column(
        # A VARCHAR storing the VALUES with a real CHECK, never a native enum
        # type, so adding a state stays an ordinary migration. `create_constraint`
        # is explicit because SQLAlchemy 2 defaults it to False.
        SAEnum(
            DebriefState,
            native_enum=False,
            length=16,
            create_constraint=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        comment="building | ready | failed | empty",
    )
    claim_owner: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="Token of the builder holding this row; a settle quotes it or is refused.",
    )
    held_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Not available before this instant: a building lease, or a failed cooldown.",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name_key", name="uq_relation_debriefs_user_name"),
        # The chat directory reads "which relationships of mine have a debrief
        # to inject", which is this index and nothing else.
        Index("ix_relation_debriefs_user_state", "user_id", "state"),
    )

    def __repr__(self) -> str:
        return f"<RelationDebrief(user={self.user_id}, key={self.name_key!r}, {self.state})>"
