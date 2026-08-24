"""Drop the two demoted reasoning-shape columns (ADR-245).

``reasoning_widget`` and ``reasoning_budget_range`` discriminated the four
stored shapes of ``reasoning_effort``. ADR-245 replaced those shapes with one
intent and derived the translator family from ``(provider, model)``, which left
both columns readable by nobody. They were kept for one release as
"descriptive" -- and the catalogue admin went on offering them for editing,
which is worse than not having them: a field an operator can curate, that
changes nothing, is a trap with a form control.

What survives is what the runtime consults: ``reasoning_enum_values`` -- the
ladder narrowing, in the intent vocabulary since ``e4f5a6b7c8d9`` -- and
``reasoning_doc_i18n_key`` for the help text.

The ``llm_reasoning_widget_enum`` type goes with its only column.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-08-27 09:00:00.000000
"""

import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")

_WIDGET_VALUES = ("none", "enum", "budget_int", "toggle_budget")


def upgrade() -> None:
    """Drop both columns, then the enum type they were the only user of."""
    bind = op.get_bind()
    carried = bind.execute(
        sa.text("SELECT count(*) FROM llm_models WHERE reasoning_budget_range IS NOT NULL")
    ).scalar_one()

    op.drop_column("llm_models", "reasoning_budget_range")
    op.drop_column("llm_models", "reasoning_widget")
    # The type is dropped explicitly: dropping a column does not remove the
    # enum it referenced, and a leftover type makes the next `alembic check`
    # report drift on a database nobody changed.
    postgresql.ENUM(name="llm_reasoning_widget_enum").drop(bind, checkfirst=True)

    # The surviving column's comment named the column being dropped. Comments
    # are part of the schema here (audit F042: they are reconciled against the
    # models, not tolerated), so the migration that removes the reference must
    # also rewrite the sentence that made it.
    op.alter_column(
        "llm_models",
        "reasoning_enum_values",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        comment=(
            "The levels this model accepts, ascending, in the ADR-245 ladder "
            "vocabulary. It may only NARROW its family's ladder "
            "(resolve_reasoning_profile); NULL = the family's own applies. The "
            "one catalogue value the reasoning resolution reads."
        ),
    )

    logger.info(
        "reasoning shape columns dropped (budget ranges discarded: %d)",
        carried,
    )


def downgrade() -> None:
    """Recreate both columns, empty.

    The values are NOT reconstructed: the widget was derivable from the shape
    of a stored ``reasoning_effort``, and those shapes no longer exist, so any
    value written here would be a guess. Both columns are nullable on the way
    back (``reasoning_widget`` was ``NOT NULL DEFAULT 'none'``, which the
    default restores for new rows) and nothing reads either of them, so an
    empty restoration is faithful rather than lossy.
    """
    widget = postgresql.ENUM(*_WIDGET_VALUES, name="llm_reasoning_widget_enum")
    widget.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "llm_models",
        sa.Column(
            "reasoning_widget",
            widget,
            nullable=False,
            server_default="none",
            comment="UI widget shape for reasoning_effort selection",
        ),
    )
    op.alter_column(
        "llm_models",
        "reasoning_enum_values",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        comment=(
            "Ordered list of accepted reasoning_effort string values "
            "(when reasoning_widget='enum')"
        ),
    )
    op.add_column(
        "llm_models",
        sa.Column(
            "reasoning_budget_range",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                '{"min":int,"max":int,"off_sentinel":int|null,"dynamic_sentinel":int|null} '
                'when reasoning_widget in ("budget_int","toggle_budget")'
            ),
        ),
    )
