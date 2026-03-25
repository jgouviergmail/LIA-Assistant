"""Optimize journal system: reduce entry size, purge old prose entries.

Part of the journal optimization overhaul:
- Reduce journal_max_entry_chars default from 2000 to 800 (directive format is compact)
- Purge all existing journal entries (old prose format incompatible with new directives)
- Reset consolidation timestamps for fresh cycles

Revision ID: journal_optimization_purge_001
Revises: user_mcp_iterative_mode_001
Create Date: 2026-03-25
"""

import sqlalchemy as sa  # noqa: F401
from alembic import op

revision = "journal_optimization_purge_001"
down_revision = "user_mcp_iterative_mode_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Reduce entry size default, purge old entries, reset consolidation."""
    # 1. Update server_default for new entry size limit
    op.alter_column(
        "users",
        "journal_max_entry_chars",
        server_default="800",
    )

    # 2. Update users still on the old default (2000) to the new default (800)
    op.execute(
        sa.text(
            "UPDATE users SET journal_max_entry_chars = 800 " "WHERE journal_max_entry_chars = 2000"
        )
    )

    # 3. Purge all existing journal entries (old prose format incompatible)
    op.execute(sa.text("DELETE FROM journal_entries"))

    # 4. Reset consolidation timestamps so users get fresh cycles
    op.execute(sa.text("UPDATE users SET journal_last_consolidated_at = NULL"))


def downgrade() -> None:
    """Restore old entry size default (purged entries cannot be restored)."""
    op.alter_column(
        "users",
        "journal_max_entry_chars",
        server_default="2000",
    )

    op.execute(
        sa.text(
            "UPDATE users SET journal_max_entry_chars = 2000 " "WHERE journal_max_entry_chars = 800"
        )
    )
