"""LIA's voices are kept per voice provider: the column says so (ADR-345 amendment 2026-10-16).

Revision ID: 1ed6c591761a
Revises: c8d1f4260e77
Create Date: 2026-10-16 13:00:00.000000

A person's choice of LIA's voices was kept per provider AND model, so a model
change of the chat's slot gave them the instance's voices back although every
model of a provider offers the same voices. It is kept per provider now; an
entry an older release kept per model is still read and replaced at the next
save (``domains/voice/engine_voices.stored_choice``), so no row is rewritten
here — only the column's comment, which named the old key.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1ed6c591761a"
down_revision: str | None = "c8d1f4260e77"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PER_MODEL = (
    "The voices LIA speaks with in the chat for this account, per voice engine "
    "(provider/model): {engine: {male, female}}. A gender left out speaks with the "
    "instance's voice."
)
_PER_PROVIDER = (
    "The voices LIA speaks with in the chat for this account, per voice provider: "
    "{provider: {male, female}} (an entry keyed provider/model by an older release is "
    "read until the next save). A gender left out speaks with the instance's voice."
)


def upgrade() -> None:
    """Name the key the choice is kept under now."""
    op.alter_column(
        "users",
        "lia_voices",
        existing_type=postgresql.JSONB(),
        existing_nullable=True,
        comment=_PER_PROVIDER,
        existing_comment=_PER_MODEL,
    )


def downgrade() -> None:
    """Name the per-model key again (the rows are what each release wrote)."""
    op.alter_column(
        "users",
        "lia_voices",
        existing_type=postgresql.JSONB(),
        existing_nullable=True,
        comment=_PER_MODEL,
        existing_comment=_PER_PROVIDER,
    )
