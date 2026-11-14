"""Retain a Live reservation until its cross-worker work has actually settled.

Revision ID: a5810c2d4e61
Revises: f4709b1c3d50
"""

from alembic import op
import sqlalchemy as sa

revision = "a5810c2d4e61"
down_revision = "f4709b1c3d50"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add content-free child ownership, separate from the graph execution slot."""
    op.create_table(
        "conversation_reservation_work",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "activity_id",
            sa.Uuid(),
            sa.ForeignKey("conversation_executions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("worker_id", sa.Uuid(), nullable=False),
        sa.Column("owner_token", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("phase", sa.String(7), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "phase IN ('running', 'unknown', 'closed')", name="conversation_reservation_work_phase"
        ),
        sa.CheckConstraint(
            "purpose IN ('opening', 'request', 'closing', 'relay')",
            name="ck_conversation_reservation_work_purpose",
        ),
        sa.CheckConstraint(
            "(phase = 'closed') = (closed_at IS NOT NULL)",
            name="ck_conversation_reservation_work_closed_at",
        ),
    )
    op.create_index(
        "ix_conversation_reservation_work_activity_phase",
        "conversation_reservation_work",
        ["activity_id", "phase"],
    )


def downgrade() -> None:
    """Never discard an outstanding voice writer during rollback."""
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM conversation_reservation_work WHERE phase <> 'closed') "
            "OR EXISTS (SELECT 1 FROM conversation_executions WHERE kind = 'live' AND phase <> 'closed')"
        )
    ):
        raise RuntimeError("Resolve Live reservation work before downgrade")
    op.drop_table("conversation_reservation_work")
