"""The person's egress grants: one host a sandbox script may reach (ADR-298).

A decision taken on a HITL card — « this host, with or without the turn's
data » — remembered per account so the next run needs no question. Unique
per (account, host): answering twice updates the scope. Goes with the
account (CASCADE), untouched by a conversation reset (a table, not a Redis
family).

Revision ID: c9e5a7b1d3f4
Revises: b8d4f6c0e2a3
Create Date: 2026-09-18 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c9e5a7b1d3f4"
down_revision: str | None = "b8d4f6c0e2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HOST_COMMENT = "The exact lowercase hostname the proxy matches (ADR-298)."
_SHARE_COMMENT = (
    "Whether the turn's collected data may reach a script that declares this host; "
    "the run takes the MINIMUM over its hosts."
)
_LAST_USED_COMMENT = "When a run last declared this host under the grant."


def upgrade() -> None:
    """Create the grants table."""
    op.create_table(
        "sandbox_egress_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("host", sa.String(length=253), nullable=False, comment=_HOST_COMMENT),
        sa.Column("share_turn_data", sa.Boolean(), nullable=False, comment=_SHARE_COMMENT),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=_LAST_USED_COMMENT,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "host", name="uq_sandbox_egress_grants_user_host"),
    )
    op.create_index(
        op.f("ix_sandbox_egress_grants_user_id"),
        "sandbox_egress_grants",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the grants table — the decisions are lost, the capability asks again."""
    op.drop_index(op.f("ix_sandbox_egress_grants_user_id"), table_name="sandbox_egress_grants")
    op.drop_table("sandbox_egress_grants")
