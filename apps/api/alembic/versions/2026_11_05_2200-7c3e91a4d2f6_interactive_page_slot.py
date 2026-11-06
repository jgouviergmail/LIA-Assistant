"""A page's writer gets a slot of its own, starting on the row documents had (ADR-370).

Revision ID: 7c3e91a4d2f6
Revises: e4a1c7b92d3f
Create Date: 2026-11-05 22:00:00.000000

Pages were written on the ``document_generation`` slot, so tuning one moved the other.
The new slot starts on that row: nothing an administrator chose changes until they
change it, and an instance with no row stays on the code default, which is the same for
both. Nobody saved this row, so ``updated_by`` stays empty, and a row already there is
kept. The downgrade removes the page's row: the former code has no slot to read it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c3e91a4d2f6"
down_revision: str | None = "e4a1c7b92d3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_START_ON_THE_DOCUMENT_ROW = sa.text("""
    INSERT INTO llm_config_overrides (
        id, llm_type, provider, model, temperature, top_p, frequency_penalty, presence_penalty,
        max_tokens, timeout_seconds, context_window, reasoning_effort, provider_config,
        created_at, updated_at
    )
    SELECT
        gen_random_uuid(), 'interactive_page', provider, model, temperature, top_p,
        frequency_penalty, presence_penalty, max_tokens, timeout_seconds, context_window,
        reasoning_effort, provider_config, now(), now()
    FROM llm_config_overrides
    WHERE llm_type = 'document_generation'
    ON CONFLICT (llm_type) DO NOTHING
""")


def upgrade() -> None:
    """Start the page's slot on the row documents had."""
    op.execute(_START_ON_THE_DOCUMENT_ROW)


def downgrade() -> None:
    """Remove the page's row."""
    op.execute("DELETE FROM llm_config_overrides WHERE llm_type = 'interactive_page'")
