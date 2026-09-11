"""Anticipated moments — LIA comes back at an instant, not at a tick.

The heartbeat draws a random batch of accounts every thirty minutes and reads a
calendar window that starts at ``now`` and looks FORWARD, so a finished meeting
is invisible to it by construction. A moment row says « at this instant there
will be something to say to this person about this thing », is claimed by
exactly one worker when it falls due, and is settled from an explicit result.

Three properties of the table, each paid for elsewhere in this repository:

- ``uq_proactive_moments_identity`` — the detector re-reads the same calendar
  window every five minutes, so without a unique key it would file the same
  event at every pass.
- ``ix_proactive_moments_due_pending`` — partial on purpose: the sweep scans
  pending rows and nothing else, and within a day the settled rows outnumber
  them by orders of magnitude.
- ``kind`` and ``state`` are ``String``, not native enums. A bare enum member as
  the RESULT of a SQL expression binds as ``NullType`` and sends its VALUE where
  the column stores its NAME (measured 2026-09-05, ADR-276) — a String column
  cannot fall into it.

The table is NOT a register: settled rows are purged after
``MOMENTS_RETENTION_DAYS``. What LIA actually did outlives it in
``agent_effects`` and ``heartbeat_notifications``.

Revision ID: b4f2a1c9d3e7
Revises: 39c7e93d85b1
Create Date: 2026-09-11 08:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b4f2a1c9d3e7"
down_revision: str | None = "39c7e93d85b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KIND_COMMENT = "MomentKind value — String, never a native enum (NullType trap)."
_SOURCE_REF_COMMENT = "What the moment is about, in the source's own vocabulary."
_DUE_AT_COMMENT = "When there will be something to say (UTC)."
_NOT_AFTER_COMMENT = (
    "When there no longer will be — the row expires instead of arriving late."
)
_STATE_COMMENT = "MomentState value."
_CLAIM_OWNER_COMMENT = (
    "Owner token of the worker holding this row; every settle quotes it."
)
_SKIP_REASON_COMMENT = "MomentSkipReason value when the state is 'skipped'."
_PAYLOAD_COMMENT = "Deduplication and scoring only — never the people involved."


def upgrade() -> None:
    """Create the table, its identity constraint and its partial due index."""
    op.create_table(
        "proactive_moments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False, comment=_KIND_COMMENT),
        sa.Column(
            "source_ref",
            sa.String(length=255),
            nullable=False,
            comment=_SOURCE_REF_COMMENT,
        ),
        sa.Column(
            "due_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment=_DUE_AT_COMMENT,
        ),
        sa.Column(
            "not_after",
            sa.DateTime(timezone=True),
            nullable=False,
            comment=_NOT_AFTER_COMMENT,
        ),
        sa.Column(
            "state",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
            comment=_STATE_COMMENT,
        ),
        sa.Column(
            "claim_owner",
            sa.String(length=64),
            nullable=True,
            comment=_CLAIM_OWNER_COMMENT,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "skip_reason",
            sa.String(length=64),
            nullable=True,
            comment=_SKIP_REASON_COMMENT,
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment=_PAYLOAD_COMMENT,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "user_id",
            "kind",
            "source_ref",
            name="uq_proactive_moments_identity",
        ),
    )
    op.create_index(
        "ix_proactive_moments_user_id",
        "proactive_moments",
        ["user_id"],
    )
    op.create_index(
        "ix_proactive_moments_due_pending",
        "proactive_moments",
        ["due_at"],
        postgresql_where=sa.text("state = 'pending'"),
    )


def downgrade() -> None:
    """Drop the table and both indexes."""
    op.drop_index("ix_proactive_moments_due_pending", table_name="proactive_moments")
    op.drop_index("ix_proactive_moments_user_id", table_name="proactive_moments")
    op.drop_table("proactive_moments")
