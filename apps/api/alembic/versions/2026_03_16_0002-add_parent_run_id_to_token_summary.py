"""Add parent_run_id to message_token_summary.

Revision ID: sub_agents_002
Revises: sub_agents_001
Create Date: 2026-03-16

Adds parent_run_id column to message_token_summary for sub-agent cost attribution.
When a sub-agent runs in background mode, its token summary links back to the
parent turn that spawned it. This enables hierarchical cost queries:
"How much did this sub-agent cost when triggered by this turn?"

The column is nullable (most token summaries have no parent) and indexed
for efficient lookups.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "sub_agents_002"
down_revision: str | None = "sub_agents_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add parent_run_id column with index."""
    op.add_column(
        "message_token_summary",
        sa.Column(
            "parent_run_id",
            sa.String(255),
            nullable=True,
            comment="Parent run_id for sub-agent background executions (cost attribution)",
        ),
    )
    op.create_index(
        "ix_message_token_summary_parent_run_id",
        "message_token_summary",
        ["parent_run_id"],
        postgresql_where=sa.text("parent_run_id IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove parent_run_id column."""
    op.drop_index(
        "ix_message_token_summary_parent_run_id",
        table_name="message_token_summary",
    )
    op.drop_column("message_token_summary", "parent_run_id")
