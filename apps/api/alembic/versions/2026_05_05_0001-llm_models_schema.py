"""Schema for the new llm_models catalogue + nullable linkage columns.

Step 1 of 3 toward making the LLM model catalogue DB-driven.

This migration adds:
- A new ``llm_provider_enum`` PostgreSQL enum (7 values).
- A new ``llm_models`` table with capability columns.
- A nullable ``model_id`` FK column on ``llm_model_pricing`` (NOT NULL set
  by migration #3 once backfill (#2) has populated it).
- A nullable ``provider`` column on ``image_generation_pricing`` (NOT NULL
  set by migration #3).

Reference: docs/superpowers/specs/2026-05-05-llm-models-db-source-of-truth-design.md

Revision ID: llm_models_001
Revises: health_metrics_005
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "llm_models_001"
down_revision: str | None = "health_metrics_005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen list of provider values. MUST stay in sync with LLMProviderEnum
# (apps/api/src/domains/llm/models.py) AND LLM_PROVIDERS
# (apps/api/src/domains/llm_config/constants.py).
PROVIDER_VALUES: tuple[str, ...] = (
    "openai",
    "anthropic",
    "deepseek",
    "perplexity",
    "ollama",
    "gemini",
    "qwen",
)


def upgrade() -> None:
    """Create llm_models + add nullable linkage columns to existing pricing tables."""
    # 1. Provider enum (created once, referenced by both tables)
    provider_enum = postgresql.ENUM(
        *PROVIDER_VALUES,
        name="llm_provider_enum",
        create_type=True,
    )
    provider_enum.create(op.get_bind(), checkfirst=True)

    # 2. llm_models — catalogue with capability metadata, mutated in place
    op.create_table(
        "llm_models",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "provider",
            postgresql.ENUM(
                *PROVIDER_VALUES,
                name="llm_provider_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("max_input_tokens", sa.Integer(), nullable=False, server_default="8192"),
        sa.Column("max_output_tokens", sa.Integer(), nullable=False, server_default="4096"),
        sa.Column("supports_tools", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "supports_structured_output",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "supports_strict_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "supports_streaming",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "supports_vision",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "is_reasoning_model",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("model_name", name="uq_llm_models_model_name"),
    )
    # Note: model_name already gets a unique index from UniqueConstraint above.
    # is_active is a low-cardinality boolean; the planner will skip a standalone
    # index. The cache loads the full active set in one query (~30 rows), so a
    # sequential scan is faster anyway. If we ever query by (provider, is_active)
    # at scale, consider a partial composite index then.
    op.create_index("ix_llm_models_provider", "llm_models", ["provider"])

    # 3. llm_model_pricing — add nullable FK column (NOT NULL set by migration #3)
    op.add_column(
        "llm_model_pricing",
        sa.Column("model_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_llm_model_pricing_model_id",
        "llm_model_pricing",
        "llm_models",
        ["model_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_llm_model_pricing_model_id",
        "llm_model_pricing",
        ["model_id"],
    )

    # 4. image_generation_pricing — add nullable provider column
    op.add_column(
        "image_generation_pricing",
        sa.Column(
            "provider",
            postgresql.ENUM(
                *PROVIDER_VALUES,
                name="llm_provider_enum",
                create_type=False,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_image_generation_pricing_provider",
        "image_generation_pricing",
        ["provider"],
    )


def downgrade() -> None:
    """Drop everything in reverse order."""
    op.drop_index("ix_image_generation_pricing_provider", table_name="image_generation_pricing")
    op.drop_column("image_generation_pricing", "provider")

    op.drop_index("ix_llm_model_pricing_model_id", table_name="llm_model_pricing")
    op.drop_constraint("fk_llm_model_pricing_model_id", "llm_model_pricing", type_="foreignkey")
    op.drop_column("llm_model_pricing", "model_id")

    op.drop_index("ix_llm_models_provider", table_name="llm_models")
    op.drop_table("llm_models")

    # Drop the enum last (was used by both tables). Mirror the create() call
    # using postgresql.ENUM so the dialect-specific DROP TYPE is emitted.
    postgresql.ENUM(*PROVIDER_VALUES, name="llm_provider_enum").drop(op.get_bind(), checkfirst=True)
