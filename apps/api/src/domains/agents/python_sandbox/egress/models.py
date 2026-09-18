"""The person's egress grants (ADR-298).

A grant is a decision the person took on a HITL card — « this host, with or
without the turn's data » — and it is remembered so the next run needs no
question. It is the account's: it goes with the account, never with a
conversation, and a reset (a Redis purge by family) cannot reach a table.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.domains.agents.python_sandbox.egress.hosts import MAX_HOST_LENGTH
from src.infrastructure.database.models import BaseModel

#: Column comments, shared with the migration — the replay check compares them.
HOST_COMMENT = "The exact lowercase hostname the proxy matches (ADR-298)."
SHARE_COMMENT = (
    "Whether the turn's collected data may reach a script that declares this host; "
    "the run takes the MINIMUM over its hosts."
)
LAST_USED_COMMENT = "When a run last declared this host under the grant."


class SandboxEgressGrant(BaseModel):
    """One host the person allowed a sandbox script to reach.

    Attributes:
        user_id: Whose grant. Every read filters on it.
        host: The exact hostname, as the proxy matches it.
        share_turn_data: The scope the person chose on the card.
        last_used_at: The last run that relied on it, for the settings list.
    """

    __tablename__ = "sandbox_egress_grants"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    host: Mapped[str] = mapped_column(String(MAX_HOST_LENGTH), nullable=False, comment=HOST_COMMENT)
    share_turn_data: Mapped[bool] = mapped_column(Boolean, nullable=False, comment=SHARE_COMMENT)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment=LAST_USED_COMMENT
    )

    __table_args__ = (
        # One decision per host per account: answering the card twice for the
        # same host updates the scope, it never makes a second row.
        UniqueConstraint("user_id", "host", name="uq_sandbox_egress_grants_user_host"),
    )


__all__ = ["HOST_COMMENT", "LAST_USED_COMMENT", "SHARE_COMMENT", "SandboxEgressGrant"]
