"""Observation columns on token_usage_logs (ADR-244, Lot 0b).

Four nullable columns and one index. No backfill: they describe calls made
after this migration, and inventing history would be worse than admitting its
absence. ``llm_type`` is the configured slot, from the closed
LLM_TYPES_REGISTRY vocabulary -- aggregates group by it and never by
``node_name``, which carries 101 distinct unbounded values, some of them prompt
fragments.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-08-25 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the four observation columns and the controller-window index."""
    op.add_column(
        "token_usage_logs",
        sa.Column(
            "latency_ms",
            sa.Integer(),
            nullable=True,
            comment="Wall time of the LLM call in milliseconds",
        ),
    )
    op.add_column(
        "token_usage_logs",
        sa.Column("status", sa.String(length=16), nullable=True, comment="success / error"),
    )
    op.add_column(
        "token_usage_logs",
        sa.Column(
            "failure_kind",
            sa.String(length=32),
            nullable=True,
            comment="LLM_FAILURE_KINDS member when status='error', NULL otherwise",
        ),
    )
    op.add_column(
        "token_usage_logs",
        sa.Column(
            "llm_type",
            sa.String(length=64),
            nullable=True,
            comment=(
                "The configured slot from LLM_TYPES_REGISTRY. Aggregates group by "
                "this, never by node_name, whose values are unbounded free text"
            ),
        ),
    )
    op.create_index(
        "ix_token_usage_logs_controller_window",
        "token_usage_logs",
        ["llm_type", "model_name", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    """Drop the index and the four columns."""
    op.drop_index("ix_token_usage_logs_controller_window", table_name="token_usage_logs")
    for column in ("llm_type", "failure_kind", "status", "latency_ms"):
        op.drop_column("token_usage_logs", column)
