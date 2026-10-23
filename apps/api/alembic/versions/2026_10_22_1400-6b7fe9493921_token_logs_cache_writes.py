"""Keep each call's prompt-cache writes on its token log row (ADR-362).

A write is a prompt token billed above the input price — 1.25x for Claude's
five-minute lifetime, 2x for its one hour — so the row's three token counts and
its tariff no longer rebuilt its cost: the surcharge lived in ``cost_usd`` alone
(ADR-306, stated limit). The two columns close that limit: the writes, and the
part of them written for the extended lifetime.

Nullable with no backfill, like the ADR-244 observation columns: an older row's
writes are inside its cost but were never counted, and NULL says so rather than
a zero nobody measured. Adding a nullable column without a default rewrites
nothing, whatever the size of the table.

Revision ID: 6b7fe9493921
Revises: 1173db815a53
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6b7fe9493921"
down_revision: str | None = "1173db815a53"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "token_usage_logs",
        sa.Column(
            "cache_write_tokens",
            sa.Integer(),
            nullable=True,
            comment="Prompt tokens written to the provider's prompt cache (part of prompt_tokens)",
        ),
    )
    op.add_column(
        "token_usage_logs",
        sa.Column(
            "cache_write_extended_tokens",
            sa.Integer(),
            nullable=True,
            comment="The part of cache_write_tokens written for the provider's extended lifetime",
        ),
    )


def downgrade() -> None:
    op.drop_column("token_usage_logs", "cache_write_extended_tokens")
    op.drop_column("token_usage_logs", "cache_write_tokens")
