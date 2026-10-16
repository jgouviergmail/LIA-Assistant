"""Add the Fish Audio provider to ``llm_provider_enum`` (ADR-345).

Revision ID: cec87eda4868
Revises: 0ff858a07321
Create Date: 2026-10-14 10:00:00.000000

The enum label commits in its own autocommit block, before the migration that
inserts the Fish Audio catalogue rows uses it: PostgreSQL refuses a value added
in the same transaction that reads it. The downgrade keeps the label, as the
``typesafe`` migration does — PostgreSQL cannot drop a used enum label safely,
and an unused one costs nothing.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cec87eda4868"
down_revision: str | None = "0ff858a07321"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Commit the new provider label before anything reads it."""
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE llm_provider_enum ADD VALUE IF NOT EXISTS 'fishaudio'")


def downgrade() -> None:
    """Keep the label: dropping an enum value is unsafe once a row may hold it."""
