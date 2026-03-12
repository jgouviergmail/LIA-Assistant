"""Add user memory preference and embedding model pricing

Revision ID: add_user_memory_pref_001
Revises: add_user_home_location_001
Create Date: 2025-12-21 00:00:00.000000

This migration:
1. Adds memory_enabled field to users table for per-user memory control
2. Adds OpenAI embedding model pricing for cost tracking:
   - text-embedding-3-small: $0.02 per 1M tokens
   - text-embedding-3-large: $0.13 per 1M tokens

The memory_enabled preference allows users to toggle long-term memory
(extraction + injection) via UI toggle in header.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_user_memory_pref_001"
down_revision: str | None = "add_user_home_location_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add memory_enabled column to users table and seed embedding pricing.
    """
    # 1. Add memory_enabled column with server default True
    op.add_column(
        "users",
        sa.Column(
            "memory_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="User preference for long-term memory (extraction + injection). True = enabled by default.",
        ),
    )

    # 2. Seed OpenAI embedding model pricing
    now = datetime.now(UTC)
    conn = op.get_bind()

    embedding_pricing = [
        # text-embedding-3-small: $0.02 per 1M tokens (most cost-effective)
        {
            "model_name": "text-embedding-3-small",
            "input": 0.02,
            "cached": None,  # Embeddings don't have cached pricing
            "output": 0.0,  # Embeddings only consume input tokens
        },
        # text-embedding-3-large: $0.13 per 1M tokens (higher quality)
        {
            "model_name": "text-embedding-3-large",
            "input": 0.13,
            "cached": None,
            "output": 0.0,
        },
        # Legacy ada model for completeness
        {
            "model_name": "text-embedding-ada-002",
            "input": 0.10,
            "cached": None,
            "output": 0.0,
        },
    ]

    for pricing in embedding_pricing:
        conn.execute(
            text("""
                INSERT INTO llm_model_pricing (
                    id,
                    model_name,
                    input_price_per_1m_tokens,
                    cached_input_price_per_1m_tokens,
                    output_price_per_1m_tokens,
                    effective_from,
                    is_active,
                    created_at,
                    updated_at
                ) VALUES (
                    gen_random_uuid(),
                    :model_name,
                    :input,
                    :cached,
                    :output,
                    :effective_from,
                    true,
                    :created_at,
                    :updated_at
                )
                ON CONFLICT (model_name, effective_from) DO NOTHING
            """),
            {
                "model_name": pricing["model_name"],
                "input": pricing["input"],
                "cached": pricing["cached"],
                "output": pricing["output"],
                "effective_from": now,
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    """
    Remove memory_enabled column and embedding pricing.
    """
    # Remove embedding pricing
    conn = op.get_bind()
    embedding_models = [
        "text-embedding-3-small",
        "text-embedding-3-large",
        "text-embedding-ada-002",
    ]
    for model_name in embedding_models:
        conn.execute(
            text("DELETE FROM llm_model_pricing WHERE model_name = :model_name"),
            {"model_name": model_name},
        )

    # Remove memory_enabled column
    op.drop_column("users", "memory_enabled")
