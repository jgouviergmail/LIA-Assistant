"""Keep graph admission and voice reservations independently of transport TTLs.

Revision ID: c58d9e2f4a61
Revises: b43c6d9e1a72
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c58d9e2f4a61"
down_revision: str | Sequence[str] | None = "b43c6d9e1a72"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add content-free authority; a Live reservation does not consume a graph slot."""
    op.create_table(
        "conversation_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_revision", sa.BigInteger(), nullable=False),
        sa.Column("runtime_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_kind", sa.String(9), nullable=False),
        sa.Column("kind", sa.String(5), nullable=False),
        sa.Column("phase", sa.String(10), nullable=False),
        sa.Column("fence", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("owner_token", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.String(255), nullable=False),
        sa.Column("stream_id", sa.String(255), nullable=False),
        sa.Column("relayed", sa.Boolean(), nullable=False),
        sa.Column("cancellable", sa.Boolean(), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "conversation_kind IN ('main', 'secondary')", name="execution_conversation_kind"
        ),
        sa.CheckConstraint("kind IN ('graph', 'live')", name="conversation_execution_kind"),
        sa.CheckConstraint(
            "phase IN ('running', 'draining', 'recovering', 'closed')",
            name="conversation_execution_phase",
        ),
        sa.CheckConstraint("conversation_revision >= 0", name="ck_execution_revision"),
        sa.CheckConstraint("fence > 0", name="ck_execution_fence"),
        sa.CheckConstraint(
            "(phase = 'closed') = (closed_at IS NOT NULL)", name="ck_execution_closed_at"
        ),
    )
    op.create_index(
        "uq_conversation_execution_active_owner_kind",
        "conversation_executions",
        ["user_id", "kind"],
        unique=True,
        postgresql_where=sa.text("phase <> 'closed'"),
    )
    op.create_index(
        "ix_conversation_executions_runtime_phase",
        "conversation_executions",
        ["runtime_id", "phase"],
    )
    op.create_index(
        "uq_conversation_execution_owner_stream",
        "conversation_executions",
        ["user_id", "stream_id"],
        unique=True,
    )


def downgrade() -> None:
    """Never erase authority while a producer or its recovery still occupies it."""
    active = op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM conversation_executions WHERE phase <> 'closed')")
    )
    if active:
        raise RuntimeError("Close or recover active conversation executions before downgrading")
    op.drop_table("conversation_executions")
