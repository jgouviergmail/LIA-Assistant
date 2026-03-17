"""Create sub_agents table.

Revision ID: sub_agents_001
Revises: rag_spaces_002
Create Date: 2026-03-16

Persistent specialized sub-agents that the principal assistant can delegate
tasks to. Each sub-agent is owned by a user and has its own configuration
(LLM, tools, skills, timeouts). V1 sub-agents are read-only.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "sub_agents_001"
down_revision: str | None = "rag_spaces_002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create sub_agents table with indexes."""
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
        # LLM overrides (null = inherit from settings defaults)
        sa.Column("llm_provider", sa.String(50), nullable=True),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("llm_temperature", sa.Float(), nullable=True),
        # Execution limits
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
        # Skills & tools (JSONB arrays)
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
        # Status
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
        # Provenance
        sa.Column(
            "created_by",
            sa.String(20),
            nullable=False,
            server_default="user",
        ),
        sa.Column("template_id", sa.String(50), nullable=True),
        # Execution tracking
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
        # Constraints
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Standard index on user_id
    op.create_index("ix_sub_agents_user_id", "sub_agents", ["user_id"])

    # Unique constraint: one name per user
    op.create_index(
        "ix_sub_agents_user_name",
        "sub_agents",
        ["user_id", "name"],
        unique=True,
    )

    # Partial index for enabled sub-agents (hot path for tool catalogue)
    op.create_index(
        "ix_sub_agents_enabled",
        "sub_agents",
        ["user_id"],
        postgresql_where=sa.text("is_enabled = true"),
    )


def downgrade() -> None:
    """Drop sub_agents table."""
    op.drop_index("ix_sub_agents_enabled", table_name="sub_agents")
    op.drop_index("ix_sub_agents_user_name", table_name="sub_agents")
    op.drop_index("ix_sub_agents_user_id", table_name="sub_agents")
    op.drop_table("sub_agents")
