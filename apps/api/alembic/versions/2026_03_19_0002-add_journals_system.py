"""Add Personal Journals (Carnets de Bord) system.

Revision ID: journals_001
Revises: system_rag_spaces_001
Create Date: 2026-03-19

Creates the journal_entries table and adds journal settings to users:
1. journal_entries table with FK to users, embeddings, indexes
2. User settings columns (enable/disable, size limits, cost tracking)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "journals_001"
down_revision: str | None = "system_rag_spaces_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add journals system: table + user settings."""
    # ====================================================================
    # 1. Create journal_entries table
    # ====================================================================
    op.create_table(
        "journal_entries",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("theme", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "mood",
            sa.String(20),
            nullable=False,
            server_default="reflective",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default="conversation",
        ),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("personality_code", sa.String(50), nullable=True),
        sa.Column(
            "char_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "embedding",
            ARRAY(sa.Float()),
            nullable=True,
            comment="E5-small embedding (384 dims) for semantic relevance search",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        # Constraints
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entries")),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_journal_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        comment="Assistant personal logbook entries with semantic embeddings",
    )

    # Indexes
    op.create_index(
        "ix_journal_entries_user_status_created",
        "journal_entries",
        ["user_id", "status", "created_at"],
    )
    op.create_index(
        "ix_journal_entries_user_theme",
        "journal_entries",
        ["user_id", "theme"],
    )

    # ====================================================================
    # 2. Add journal settings to users table
    # ====================================================================

    # Feature toggles
    op.add_column(
        "users",
        sa.Column(
            "journals_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Enable personal journals feature (user preference).",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "journal_consolidation_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="Enable periodic journal consolidation by the assistant.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "journal_consolidation_with_history",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment="Allow consolidation to analyze conversation history (higher cost).",
        ),
    )

    # Size limits (user-configurable)
    op.add_column(
        "users",
        sa.Column(
            "journal_max_total_chars",
            sa.Integer(),
            nullable=False,
            server_default="40000",
            comment="Max total characters across all active journal entries.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "journal_context_max_chars",
            sa.Integer(),
            nullable=False,
            server_default="1500",
            comment="Max characters for journal context injection into prompts.",
        ),
    )

    # Consolidation tracking
    op.add_column(
        "users",
        sa.Column(
            "journal_last_consolidated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of last journal consolidation for this user.",
        ),
    )

    # Cost tracking (last intervention)
    op.add_column(
        "users",
        sa.Column(
            "journal_last_cost_tokens_in",
            sa.Integer(),
            nullable=True,
            comment="Input tokens of last journal background intervention.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "journal_last_cost_tokens_out",
            sa.Integer(),
            nullable=True,
            comment="Output tokens of last journal background intervention.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "journal_last_cost_eur",
            sa.Numeric(10, 6),
            nullable=True,
            comment="Real cost in EUR of last journal background intervention.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "journal_last_cost_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp of last journal background intervention.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "journal_last_cost_source",
            sa.String(20),
            nullable=True,
            comment="Source of last journal intervention: 'extraction' or 'consolidation'.",
        ),
    )


def downgrade() -> None:
    """Remove journals system."""
    # Drop user columns (reverse order)
    op.drop_column("users", "journal_last_cost_source")
    op.drop_column("users", "journal_last_cost_at")
    op.drop_column("users", "journal_last_cost_eur")
    op.drop_column("users", "journal_last_cost_tokens_out")
    op.drop_column("users", "journal_last_cost_tokens_in")
    op.drop_column("users", "journal_last_consolidated_at")
    op.drop_column("users", "journal_context_max_chars")
    op.drop_column("users", "journal_max_total_chars")
    op.drop_column("users", "journal_consolidation_with_history")
    op.drop_column("users", "journal_consolidation_enabled")
    op.drop_column("users", "journals_enabled")

    # Drop indexes and table
    op.drop_index("ix_journal_entries_user_theme", table_name="journal_entries")
    op.drop_index("ix_journal_entries_user_status_created", table_name="journal_entries")
    op.drop_table("journal_entries")
