"""drop orphaned plan_approvals table (F042)

Revision ID: 320bf8a052a4
Revises: 423c346b3f03
Create Date: 2026-07-13 10:18:56.273652

The ``plan_approvals`` table (added by ``plan_approvals_001`` for the Phase 8
plan-level HITL audit trail) has no SQLAlchemy model any more: plan-level
approval became a pass-through (tool-level HITL supersedes it), so nothing
reads or writes the table and it is absent from ``Base.metadata``. Alembic
autogenerate therefore proposed dropping it on every ``alembic check`` run —
one of the model↔schema drifts the 2026-07-13 counter-audit flagged (F042).
This migration removes the dead table; ``downgrade`` faithfully recreates it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "320bf8a052a4"
down_revision: str | None = "423c346b3f03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the orphaned plan_approvals table and its indexes."""
    op.drop_index(op.f("ix_plan_approvals_user_decision_timestamp"), table_name="plan_approvals")
    op.drop_index(op.f("ix_plan_approvals_decision_timestamp"), table_name="plan_approvals")
    op.drop_index(op.f("ix_plan_approvals_decision"), table_name="plan_approvals")
    op.drop_index(op.f("ix_plan_approvals_conversation_id"), table_name="plan_approvals")
    op.drop_index(op.f("ix_plan_approvals_user_id"), table_name="plan_approvals")
    op.drop_table("plan_approvals")


def downgrade() -> None:
    """Recreate plan_approvals exactly as plan_approvals_001 defined it."""
    op.create_table(
        "plan_approvals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
            comment="Primary key",
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="ID of the ExecutionPlan that required approval",
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="User who made the approval decision",
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Conversation context for the plan",
        ),
        sa.Column(
            "plan_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="Plan summary (steps, costs, tools, classifications)",
        ),
        sa.Column(
            "strategies_triggered",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
            comment="Approval strategies that triggered (ManifestBased, CostThreshold, etc.)",
        ),
        sa.Column(
            "decision",
            sa.String(length=20),
            nullable=False,
            comment="User decision: APPROVE, REJECT, EDIT, REPLAN",
        ),
        sa.Column(
            "decision_timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="When the decision was made",
        ),
        sa.Column(
            "modifications",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Plan modifications applied (for EDIT decisions)",
        ),
        sa.Column(
            "rejection_reason",
            sa.Text(),
            nullable=True,
            comment="Reason for rejection (for REJECT decisions)",
        ),
        sa.Column(
            "approval_latency_seconds",
            sa.Float(),
            nullable=True,
            comment="Time from approval request to user decision (in seconds)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
            comment="Record creation timestamp",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plan_approvals")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_plan_approvals_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_plan_approvals_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        comment="Audit trail for HITL plan-level approvals (Phase 8)",
    )
    op.create_index(op.f("ix_plan_approvals_user_id"), "plan_approvals", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_plan_approvals_conversation_id"),
        "plan_approvals",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plan_approvals_decision"),
        "plan_approvals",
        ["decision"],
        unique=False,
        postgresql_ops={"decision": "text_pattern_ops"},
    )
    op.create_index(
        op.f("ix_plan_approvals_decision_timestamp"),
        "plan_approvals",
        ["decision_timestamp"],
        unique=False,
    )
    op.create_index(
        op.f("ix_plan_approvals_user_decision_timestamp"),
        "plan_approvals",
        ["user_id", "decision", "decision_timestamp"],
        unique=False,
    )
