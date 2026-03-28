"""Add image generation support: pricing table, user preferences, cost tracking columns.

Creates:
- image_generation_pricing table (per-image pricing by model/quality/size)
- User preference columns for image generation
- Cost tracking columns on message_token_summary and user_statistics

Revision ID: image_generation_001
Revises: journal_optimization_purge_001
Create Date: 2026-03-25
"""

import sqlalchemy as sa
from alembic import op

revision = "image_generation_001"
down_revision = "journal_optimization_purge_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add image generation tables, columns, and seed data."""
    # ========================================================================
    # 1. CREATE image_generation_pricing TABLE
    # ========================================================================
    op.create_table(
        "image_generation_pricing",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("model", sa.String(50), nullable=False, index=True),
        sa.Column("quality", sa.String(20), nullable=False),
        sa.Column("size", sa.String(20), nullable=False),
        sa.Column("cost_per_image_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            default=True,
            server_default=sa.text("true"),
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "model",
            "quality",
            "size",
            "effective_from",
            name="uq_image_gen_pricing_model_quality_size_effective",
        ),
        sa.Index("ix_image_gen_pricing_active_lookup", "model", "quality", "size", "is_active"),
    )

    # ========================================================================
    # 2. SEED pricing data (gpt-image-1, source: OpenAI pricing page)
    # ========================================================================
    op.execute(sa.text("""
            INSERT INTO image_generation_pricing (id, model, quality, size, cost_per_image_usd, effective_from, is_active, created_at, updated_at)
            VALUES
                (gen_random_uuid(), 'gpt-image-1', 'low',    '1024x1024', 0.011000, now(), true, now(), now()),
                (gen_random_uuid(), 'gpt-image-1', 'low',    '1536x1024', 0.016000, now(), true, now(), now()),
                (gen_random_uuid(), 'gpt-image-1', 'low',    '1024x1536', 0.016000, now(), true, now(), now()),
                (gen_random_uuid(), 'gpt-image-1', 'medium', '1024x1024', 0.042000, now(), true, now(), now()),
                (gen_random_uuid(), 'gpt-image-1', 'medium', '1536x1024', 0.063000, now(), true, now(), now()),
                (gen_random_uuid(), 'gpt-image-1', 'medium', '1024x1536', 0.063000, now(), true, now(), now()),
                (gen_random_uuid(), 'gpt-image-1', 'high',   '1024x1024', 0.167000, now(), true, now(), now()),
                (gen_random_uuid(), 'gpt-image-1', 'high',   '1536x1024', 0.250000, now(), true, now(), now()),
                (gen_random_uuid(), 'gpt-image-1', 'high',   '1024x1536', 0.250000, now(), true, now(), now())
            ON CONFLICT (model, quality, size, effective_from) DO NOTHING
        """))

    # ========================================================================
    # 3. ADD user preference columns to users table
    # ========================================================================
    op.add_column(
        "users",
        sa.Column(
            "image_generation_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "image_generation_default_quality",
            sa.String(20),
            nullable=False,
            server_default="low",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "image_generation_default_size",
            sa.String(20),
            nullable=False,
            server_default="1024x1536",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "image_generation_output_format",
            sa.String(10),
            nullable=False,
            server_default="png",
        ),
    )

    # ========================================================================
    # 4. ADD cost tracking columns to message_token_summary
    # ========================================================================
    op.add_column(
        "message_token_summary",
        sa.Column(
            "image_generation_requests",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "message_token_summary",
        sa.Column(
            "image_generation_cost_eur",
            sa.Numeric(10, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    # ========================================================================
    # 5. ADD cost tracking columns to user_statistics
    # ========================================================================
    # Lifetime totals
    op.add_column(
        "user_statistics",
        sa.Column(
            "total_image_generation_requests",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "user_statistics",
        sa.Column(
            "total_image_generation_cost_eur",
            sa.Numeric(12, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    # Current billing cycle
    op.add_column(
        "user_statistics",
        sa.Column(
            "cycle_image_generation_requests",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "user_statistics",
        sa.Column(
            "cycle_image_generation_cost_eur",
            sa.Numeric(12, 6),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    """Remove image generation support."""
    # 5. DROP user_statistics columns
    op.drop_column("user_statistics", "cycle_image_generation_cost_eur")
    op.drop_column("user_statistics", "cycle_image_generation_requests")
    op.drop_column("user_statistics", "total_image_generation_cost_eur")
    op.drop_column("user_statistics", "total_image_generation_requests")

    # 4. DROP message_token_summary columns
    op.drop_column("message_token_summary", "image_generation_cost_eur")
    op.drop_column("message_token_summary", "image_generation_requests")

    # 3. DROP user preference columns
    op.drop_column("users", "image_generation_output_format")
    op.drop_column("users", "image_generation_default_size")
    op.drop_column("users", "image_generation_default_quality")
    op.drop_column("users", "image_generation_enabled")

    # 1. DROP pricing table
    op.drop_table("image_generation_pricing")
