"""What LIA does from the Tools gets a slot of its own, starting on the digest's row (ADR-372).

Revision ID: c8e4a1f27b53
Revises: b6d21f7e4a90
Create Date: 2026-11-06 21:00:00.000000

The new slot starts on the model an instance already chose for short mail work, so a click runs on
something it pays for, until an administrator sizes it apart. The output cap is the one thing that
differs: a rewrite is as long as the text it rewrites, and the digest's cap would cut it. Nobody
saved this row, so ``updated_by`` stays empty, and a row already there is kept. An instance with no
digest row starts on the row of the response, the one model it surely pays for: the code default
needs a key the installer never asks for. With neither, the code default stands. The downgrade
removes the row: the former code has no slot to read it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8e4a1f27b53"
down_revision: str | None = "b6d21f7e4a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: ``TOOL_ASSIST_MAX_OUTPUT_TOKENS`` as this revision shipped it: a migration keeps its own value.
_OUTPUT_FLOOR = 4000

_START_ON_A_ROW_IT_PAYS_FOR = sa.text(f"""
    INSERT INTO llm_config_overrides (
        id, llm_type, provider, model, temperature, top_p, frequency_penalty, presence_penalty,
        max_tokens, timeout_seconds, context_window, reasoning_effort, provider_config,
        created_at, updated_at
    )
    SELECT
        gen_random_uuid(), 'tool_assist', provider, model, temperature, top_p,
        frequency_penalty, presence_penalty, GREATEST(max_tokens, {_OUTPUT_FLOOR}),
        timeout_seconds, context_window, reasoning_effort, provider_config, now(), now()
    FROM llm_config_overrides
    WHERE llm_type = COALESCE(
        (SELECT llm_type FROM llm_config_overrides WHERE llm_type = 'email_digest'),
        'response'
    )
    ON CONFLICT (llm_type) DO NOTHING
""")


def upgrade() -> None:
    """Start the slot on the row of the digest, else on the response's."""
    op.execute(_START_ON_A_ROW_IT_PAYS_FOR)


def downgrade() -> None:
    """Remove the slot's row."""
    op.execute("DELETE FROM llm_config_overrides WHERE llm_type = 'tool_assist'")
