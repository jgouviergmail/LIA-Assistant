"""Add llm_config_overrides.context_window, retiring OLLAMA_NUM_CTX (ADR-278).

The context window was resolved from a model NAME, and Ollama's came from a
single instance-wide environment variable handed to every tag whatever its
size: a deployment set 128 000 and a 4 B model was asked to allocate the same
window as a 27 B one. It becomes a property of the configured SLOT, nullable —
NULL means "whatever the model itself declares", which is now read from what the
server said about that tag.

The backfill exists so a deployment that HAD set the variable keeps the
behaviour it had, as a visible per-slot value rather than as a silent global:
every Ollama override row inherits the number, and only if the variable is still
present when the migration runs. Nothing is invented for an instance that never
set one.

Revision ID: c6e1523d8222
Revises: 89d81ad3b467
Create Date: 2026-09-10 08:00:00.000000
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6e1523d8222"
down_revision: str | None = "89d81ad3b467"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = (
    "Context window this slot works with, in tokens. NULL = the model's own "
    "(discovered, then catalogue, then the table). For Ollama it is also the "
    "num_ctx requested on every call (ADR-278, replacing the instance-wide "
    "OLLAMA_NUM_CTX)."
)


def _configured_num_ctx() -> int | None:
    """The retiring variable's value, when this deployment still carries it.

    Returns:
        The positive integer an operator set, or None — an empty or absent
        variable is not a value (a blank ``OLLAMA_NUM_CTX=`` was the documented
        way to say "let the model decide").
    """
    raw = (os.environ.get("OLLAMA_NUM_CTX") or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def upgrade() -> None:
    """Add the nullable column, then carry the retiring global onto its slots."""
    op.add_column(
        "llm_config_overrides",
        sa.Column("context_window", sa.Integer(), nullable=True, comment=_COMMENT),
    )

    inherited = _configured_num_ctx()
    if inherited is None:
        return
    # Only the rows the variable actually governed: it was read on the Ollama
    # branch of the provider adapter and nowhere else.
    op.execute(
        sa.text(
            "UPDATE llm_config_overrides "
            "SET context_window = :window "
            "WHERE provider = 'ollama' AND context_window IS NULL"
        ).bindparams(window=inherited)
    )


def downgrade() -> None:
    """Drop the column. The value returns to the model's own declaration."""
    op.drop_column("llm_config_overrides", "context_window")
