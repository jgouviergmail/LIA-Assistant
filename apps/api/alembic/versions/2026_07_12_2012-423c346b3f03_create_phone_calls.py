"""create phone_calls

Revision ID: 423c346b3f03
Revises: admin_broadcast_translations_001
Create Date: 2026-07-12 20:12:03.932516

Scope: create the ``phone_calls`` table only (telephony feature, P1.3).

NOTE: ``alembic revision --autogenerate`` emitted a large spurious diff against
the live schema — it tried to DROP the LangGraph checkpoint/store tables
(``checkpoints``, ``store``, ``plan_approvals``, ``checkpoint_blobs``,
``store_vectors``, …, which live outside the SQLAlchemy metadata) and churned
comments / server-defaults / non-native enums on dozens of unrelated tables
(the well-known autogenerate comparison noise). All of that was pruned; this
migration contains only the intended ``phone_calls`` create-table + indexes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "423c346b3f03"
down_revision: str | None = "admin_broadcast_translations_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "phone_calls",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("callee_display", sa.Text(), nullable=False),
        sa.Column("callee_phone", sa.Text(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("objective_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("objective_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "DIALING",
                "IN_PROGRESS",
                "COMPLETED",
                "NO_ANSWER",
                "VOICEMAIL",
                "FAILED",
                "CANCELLED",
                name="phonecallstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("elevenlabs_conversation_id", sa.Text(), nullable=True),
        sa.Column("call_seconds", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("structured_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(
                "OBJECTIVE_MET",
                "PARTIAL",
                "DECLINED",
                "UNREACHABLE",
                name="phonecalloutcome",
                native_enum=False,
                length=20,
            ),
            nullable=True,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("initiated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_phone_calls_status"), "phone_calls", ["status"], unique=False)
    op.create_index(op.f("ix_phone_calls_user_id"), "phone_calls", ["user_id"], unique=False)
    op.create_index(
        "uq_phone_calls_el_conversation",
        "phone_calls",
        ["elevenlabs_conversation_id"],
        unique=True,
        postgresql_where=sa.text("elevenlabs_conversation_id IS NOT NULL"),
    )
    op.create_index(
        "uq_phone_calls_one_active_per_user",
        "phone_calls",
        ["user_id"],
        unique=True,
        # Enum(native_enum=False) stores member NAMES → predicate must match names.
        postgresql_where=sa.text("status IN ('DIALING', 'IN_PROGRESS')"),
    )


def downgrade() -> None:
    op.drop_index("uq_phone_calls_one_active_per_user", table_name="phone_calls")
    op.drop_index("uq_phone_calls_el_conversation", table_name="phone_calls")
    op.drop_index(op.f("ix_phone_calls_user_id"), table_name="phone_calls")
    op.drop_index(op.f("ix_phone_calls_status"), table_name="phone_calls")
    op.drop_table("phone_calls")
