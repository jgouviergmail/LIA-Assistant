"""Add PostgreSQL unaccent extension.

Revision ID: add_unaccent_ext_001
Revises: add_google_api_tracking_001
Create Date: 2026-02-04

This migration enables the PostgreSQL 'unaccent' extension for accent-insensitive search.
Used for user autocomplete search that ignores accents (e.g., "Gerard" matches "Gérard").
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_unaccent_ext_001"
down_revision: str | None = "add_google_api_tracking_001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Enable the unaccent extension for accent-insensitive search."""
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")


def downgrade() -> None:
    """Remove the unaccent extension."""
    op.execute("DROP EXTENSION IF EXISTS unaccent")
