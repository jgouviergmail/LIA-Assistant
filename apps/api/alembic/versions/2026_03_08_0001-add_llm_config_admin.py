"""Add LLM configuration admin tables.

Revision ID: llm_config_001
Revises: admin_mcp_001
Create Date: 2026-03-08

Add tables for dynamic LLM configuration management:
- provider_api_keys: Encrypted API keys per LLM provider
- llm_config_overrides: Per-LLM-type config overrides
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "llm_config_001"
down_revision: str | None = "admin_mcp_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "provider_api_keys",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("encrypted_key", sa.Text(), nullable=False),
        sa.Column(
            "updated_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "llm_config_overrides",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("llm_type", sa.String(80), unique=True, nullable=False, index=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("top_p", sa.Float(), nullable=True),
        sa.Column("frequency_penalty", sa.Float(), nullable=True),
        sa.Column("presence_penalty", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("reasoning_effort", sa.String(20), nullable=True),
        sa.Column("provider_config", sa.Text(), nullable=True),
        sa.Column(
            "updated_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("llm_config_overrides")
    op.drop_table("provider_api_keys")
