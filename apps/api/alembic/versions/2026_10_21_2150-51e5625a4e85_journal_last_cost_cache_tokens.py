"""Keep the cache reads of the journal's last intervention in their own column.

The settings showed the last journal intervention as « N in / M out », N being the
prompt tokens PLUS the cache reads, while the chat meter's IN excludes them and
counts them under CACHE. The snapshot now keeps the cache reads apart, so the line
reads in the meter's vocabulary (owner request 2026-10-21).

A snapshot written before this split holds a sum that cannot be split back: it is
cleared, so no figure is ever shown under a label that does not describe it. It is
a display copy — the ledgers (``token_usage_logs``, ``message_token_summary``) keep
every call — and the next journal intervention writes it again.

The downgrade drops the column and restores the former comment; it cannot restore
the cleared snapshots.

Revision ID: 51e5625a4e85
Revises: 6b2c4e8f0a17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "51e5625a4e85"
down_revision: str | None = "6b2c4e8f0a17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TOKENS_IN_COMMENT = "Input tokens of last journal background intervention, cache reads excluded."
FORMER_TOKENS_IN_COMMENT = "Input tokens of last journal background intervention."


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "journal_last_cost_tokens_cache",
            sa.Integer(),
            nullable=True,
            comment="Cache-read input tokens of last journal background intervention.",
        ),
    )
    op.alter_column(
        "users",
        "journal_last_cost_tokens_in",
        existing_type=sa.Integer(),
        comment=TOKENS_IN_COMMENT,
        existing_comment=FORMER_TOKENS_IN_COMMENT,
        existing_nullable=True,
    )
    op.execute(
        sa.text(
            "UPDATE users SET journal_last_cost_tokens_in = NULL, "
            "journal_last_cost_tokens_out = NULL, journal_last_cost_eur = NULL, "
            "journal_last_cost_at = NULL, journal_last_cost_source = NULL "
            "WHERE journal_last_cost_at IS NOT NULL OR journal_last_cost_tokens_in IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "journal_last_cost_tokens_in",
        existing_type=sa.Integer(),
        comment=FORMER_TOKENS_IN_COMMENT,
        existing_comment=TOKENS_IN_COMMENT,
        existing_nullable=True,
    )
    op.drop_column("users", "journal_last_cost_tokens_cache")
