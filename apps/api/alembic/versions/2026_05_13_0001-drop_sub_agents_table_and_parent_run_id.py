"""Drop sub_agents table + parent_run_id column (ADR-083 Phase 2 cleanup).

Revision ID: phase_2_cleanup_001
Revises: rename_anthropic_model_ids_001
Create Date: 2026-05-13

ADR-083 Phase 2 cleanup. The /sub-agents REST API and the SubAgentExecutor
pipeline were removed (no frontend consumer; the planner's ephemeral
delegation path now runs on ReactSubAgentRunner — see ADR-083). The
`sub_agents` table held only ephemeral records cleaned up at the end of each
delegate_to_sub_agent_tool call, and the new path doesn't create ORM records
at all. Precondition audit (2026-05-13): 0 rows in prod.

`parent_run_id` (added in sub_agents_002 for hierarchical token attribution)
was never populated — the new path uses `metadata["node_name_override"]`
inside the parent TokenTrackingCallback instead. Drop the column.

`users.sub_agents_enabled` (sub_agents_003) is KEPT — still consumed by
`delegate_to_sub_agent_tool`'s preference check (the surviving SubAgentsSettings
toggle, even if currently orphaned in the UI).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "phase_2_cleanup_001"
down_revision: str | None = "rename_anthropic_model_ids_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop sub_agents table and parent_run_id column on message_token_summary."""
    # 1) parent_run_id on message_token_summary (sub_agents_002 → revert)
    op.drop_index(
        "ix_message_token_summary_parent_run_id",
        table_name="message_token_summary",
    )
    op.drop_column("message_token_summary", "parent_run_id")

    # 2) sub_agents table + its 3 indexes (sub_agents_001 → revert)
    op.drop_index("ix_sub_agents_enabled", table_name="sub_agents")
    op.drop_index("ix_sub_agents_user_name", table_name="sub_agents")
    op.drop_index("ix_sub_agents_user_id", table_name="sub_agents")
    op.drop_table("sub_agents")


def downgrade() -> None:
    """Recreate sub_agents table + parent_run_id column.

    Schema mirrors sub_agents_001 and sub_agents_002. Data is NOT restored —
    precondition audit confirmed 0 rows in prod, so there is nothing to
    recover. If a future need arises, a fresh table is enough.
    """
    # 1) sub_agents table (recreated identically to sub_agents_001).
    op.create_table(
        "sub_agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("icon", sa.String(10), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("personality_instruction", sa.Text(), nullable=True),
        sa.Column("context_instructions", sa.Text(), nullable=True),
        sa.Column("llm_provider", sa.String(50), nullable=True),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("llm_temperature", sa.Float(), nullable=True),
        sa.Column(
            "max_iterations",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default="120",
        ),
        sa.Column(
            "skill_ids",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "allowed_tools",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "blocked_tools",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="ready",
        ),
        sa.Column(
            "created_by",
            sa.String(20),
            nullable=False,
            server_default="user",
        ),
        sa.Column("template_id", sa.String(50), nullable=True),
        sa.Column(
            "execution_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_execution_summary", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sub_agents_user_id", "sub_agents", ["user_id"])
    op.create_index(
        "ix_sub_agents_user_name",
        "sub_agents",
        ["user_id", "name"],
        unique=True,
    )
    op.create_index(
        "ix_sub_agents_enabled",
        "sub_agents",
        ["user_id"],
        postgresql_where=sa.text("is_enabled = true"),
    )

    # 2) parent_run_id on message_token_summary (mirrors sub_agents_002).
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
