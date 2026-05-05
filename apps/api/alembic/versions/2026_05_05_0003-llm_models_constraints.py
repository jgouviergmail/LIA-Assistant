"""Lock down constraints + drop the legacy model_name column from pricing.

Step 3 of 3 in the LLM models DB-source-of-truth release.

After migration #2 has populated:
- ``llm_model_pricing.model_id`` (FK to llm_models)
- ``image_generation_pricing.provider``

this migration enforces the final invariants:

1. ``llm_model_pricing.model_id`` → ``NOT NULL``
2. ``llm_model_pricing.model_name`` → DROP COLUMN (info now lives on llm_models
   via JOIN; callers use ``pricing.model.model_name``)
3. ``image_generation_pricing.provider`` → ``NOT NULL``
4. Replace ``(model_name, effective_from)`` UNIQUE constraint by
   ``(model_id, effective_from)`` and rebuild the active-lookup index on
   ``(model_id, is_active)``.

Reference: docs/superpowers/specs/2026-05-05-llm-models-db-source-of-truth-design.md

Revision ID: llm_models_003
Revises: llm_models_002
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "llm_models_003"
down_revision: str | None = "llm_models_002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply NOT NULL, drop legacy column, swap constraints/indexes."""
    # 1. NOT NULL on the linkage columns (Postgres rejects if any NULL remains
    #    — should not happen post-backfill, but fails loud if it does).
    op.alter_column("llm_model_pricing", "model_id", nullable=False)
    op.alter_column("image_generation_pricing", "provider", nullable=False)

    # 2. Drop legacy unique constraint and active-lookup index that were keyed
    #    on the old model_name column.
    op.drop_constraint("uq_model_effective_from", "llm_model_pricing", type_="unique")
    op.drop_index("ix_llm_model_pricing_active_lookup", table_name="llm_model_pricing")
    op.drop_index("ix_llm_model_pricing_model_name", table_name="llm_model_pricing")

    # 3. Drop the legacy model_name column. The model name is recoverable via
    #    JOIN on llm_models (using the model_id FK).
    op.drop_column("llm_model_pricing", "model_name")

    # 4. New natural key + active-lookup index on (model_id, ...).
    op.create_unique_constraint(
        "uq_pricing_model_effective",
        "llm_model_pricing",
        ["model_id", "effective_from"],
    )
    op.create_index(
        "ix_llm_model_pricing_active_lookup",
        "llm_model_pricing",
        ["model_id", "is_active"],
    )


def downgrade() -> None:
    """Restore the legacy model_name column and old constraints/indexes."""
    # Re-add model_name as nullable first so we can backfill from llm_models.
    op.add_column(
        "llm_model_pricing",
        sa.Column("model_name", sa.String(length=100), nullable=True),
    )
    op.execute("""
        UPDATE llm_model_pricing p
        SET model_name = m.model_name
        FROM llm_models m
        WHERE p.model_id = m.id
        """)
    op.alter_column("llm_model_pricing", "model_name", nullable=False)

    # Drop the new constraints/indexes.
    op.drop_index("ix_llm_model_pricing_active_lookup", table_name="llm_model_pricing")
    op.drop_constraint("uq_pricing_model_effective", "llm_model_pricing", type_="unique")

    # Restore the legacy ones.
    op.create_index(
        "ix_llm_model_pricing_model_name",
        "llm_model_pricing",
        ["model_name"],
    )
    op.create_index(
        "ix_llm_model_pricing_active_lookup",
        "llm_model_pricing",
        ["model_name", "is_active"],
    )
    op.create_unique_constraint(
        "uq_model_effective_from",
        "llm_model_pricing",
        ["model_name", "effective_from"],
    )

    # Loosen NOT NULL constraints back to their migration #1 state.
    op.alter_column("llm_model_pricing", "model_id", nullable=True)
    op.alter_column("image_generation_pricing", "provider", nullable=True)
