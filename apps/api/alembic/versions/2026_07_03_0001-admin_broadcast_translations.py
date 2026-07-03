"""Persist broadcast translations (audit wave 3, N-213.2).

Broadcast messages were re-translated by an LLM on EVERY read (login, tab
focus) for users whose language differs from the source. Translations are
now cached in ``admin_broadcasts.message_translations`` ({language: text}): filled
at send time for all recipient languages, lazily backfilled on read for
historical broadcasts. NULL means "nothing cached yet" — the read path
falls back to lazy translation, so no backfill is needed here.

Revision ID: admin_broadcast_translations_001
Revises: anthropic_global_effort_001
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "admin_broadcast_translations_001"
down_revision: str | None = "anthropic_global_effort_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "admin_broadcasts",
        sa.Column(
            "message_translations",
            JSONB,
            nullable=True,
            comment=(
                "Cached translations {language: text}. Filled at send time, "
                "lazily backfilled on read for historical broadcasts"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("admin_broadcasts", "message_translations")
