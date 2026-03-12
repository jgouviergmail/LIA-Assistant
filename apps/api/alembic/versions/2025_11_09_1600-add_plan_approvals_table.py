"""add_plan_approvals_table

Revision ID: plan_approvals_001
Revises: user_language_001
Create Date: 2025-11-09 16:00:00.000000

Adds plan_approvals table for HITL (Human-In-The-Loop) plan-level approval audit trail.

Phase 8: HITL architecture migration from tool-level to plan-level.
Plans are now presented to users for approval BEFORE execution begins,
replacing the problematic mid-execution interrupts.

Table: plan_approvals
- Audit trail for all plan approval decisions
- Tracks approval latency, modifications, and rejection reasons
- Supports compliance and analytics
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'plan_approvals_001'
down_revision: str | None = 'user_language_001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Create plan_approvals table for HITL plan-level approval audit trail.

    Schema:
    - id: UUID primary key
    - plan_id: UUID of the ExecutionPlan
    - user_id: UUID of user who made decision (FK to users)
    - conversation_id: UUID of conversation context (FK to conversations)
    - plan_summary: JSONB with plan details (steps, costs, etc.)
    - strategies_triggered: Array of strategy names that required approval
    - decision: Approval decision type (APPROVE, REJECT, EDIT, REPLAN)
    - decision_timestamp: When decision was made
    - modifications: JSONB of plan modifications (for EDIT decisions)
    - rejection_reason: Text explaining rejection (for REJECT decisions)
    - approval_latency_seconds: Time from request to decision
    - created_at: Record creation timestamp
    """
    op.create_table(
        'plan_approvals',
        sa.Column(
            'id',
            postgresql.UUID(as_uuid=True),
            server_default=sa.text('gen_random_uuid()'),
            nullable=False,
            comment='Primary key'
        ),
        sa.Column(
            'plan_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment='ID of the ExecutionPlan that required approval'
        ),
        sa.Column(
            'user_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment='User who made the approval decision'
        ),
        sa.Column(
            'conversation_id',
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment='Conversation context for the plan'
        ),
        sa.Column(
            'plan_summary',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment='Plan summary (steps, costs, tools, classifications)'
        ),
        sa.Column(
            'strategies_triggered',
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default='{}',
            comment='Approval strategies that triggered (ManifestBased, CostThreshold, etc.)'
        ),
        sa.Column(
            'decision',
            sa.String(length=20),
            nullable=False,
            comment='User decision: APPROVE, REJECT, EDIT, REPLAN'
        ),
        sa.Column(
            'decision_timestamp',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
            comment='When the decision was made'
        ),
        sa.Column(
            'modifications',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment='Plan modifications applied (for EDIT decisions)'
        ),
        sa.Column(
            'rejection_reason',
            sa.Text(),
            nullable=True,
            comment='Reason for rejection (for REJECT decisions)'
        ),
        sa.Column(
            'approval_latency_seconds',
            sa.Float(),
            nullable=True,
            comment='Time from approval request to user decision (in seconds)'
        ),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('CURRENT_TIMESTAMP'),
            nullable=False,
            comment='Record creation timestamp'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_plan_approvals')),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            name=op.f('fk_plan_approvals_user_id_users'),
            ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['conversation_id'],
            ['conversations.id'],
            name=op.f('fk_plan_approvals_conversation_id_conversations'),
            ondelete='CASCADE'
        ),
        comment='Audit trail for HITL plan-level approvals (Phase 8)'
    )

    # Create indexes for common query patterns
    op.create_index(
        op.f('ix_plan_approvals_user_id'),
        'plan_approvals',
        ['user_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_plan_approvals_conversation_id'),
        'plan_approvals',
        ['conversation_id'],
        unique=False
    )
    op.create_index(
        op.f('ix_plan_approvals_decision'),
        'plan_approvals',
        ['decision'],
        unique=False,
        postgresql_ops={'decision': 'text_pattern_ops'}  # For LIKE queries
    )
    op.create_index(
        op.f('ix_plan_approvals_decision_timestamp'),
        'plan_approvals',
        ['decision_timestamp'],
        unique=False
    )

    # Create composite index for analytics queries
    op.create_index(
        op.f('ix_plan_approvals_user_decision_timestamp'),
        'plan_approvals',
        ['user_id', 'decision', 'decision_timestamp'],
        unique=False
    )


def downgrade() -> None:
    """
    Remove plan_approvals table and all indexes.
    """
    op.drop_index(
        op.f('ix_plan_approvals_user_decision_timestamp'),
        table_name='plan_approvals'
    )
    op.drop_index(
        op.f('ix_plan_approvals_decision_timestamp'),
        table_name='plan_approvals'
    )
    op.drop_index(
        op.f('ix_plan_approvals_decision'),
        table_name='plan_approvals'
    )
    op.drop_index(
        op.f('ix_plan_approvals_conversation_id'),
        table_name='plan_approvals'
    )
    op.drop_index(
        op.f('ix_plan_approvals_user_id'),
        table_name='plan_approvals'
    )
    op.drop_table('plan_approvals')
