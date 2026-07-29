"""Add product analytics tables (ADR-178).

``product_outcomes``: durable product truth — at most one principal outcome
per run (unique run_id), mutable E1/E2/E3 evidence, EUR cost backfilled from
message_token_summary. ``product_events``: bounded lifecycle log. Both carry
user_id and are wired into the GDPR purge map + account deletion service.

Revision ID: a8b9c0d1e2f3
Revises: f6a7b8c9d0e1
Create Date: 2026-07-29 04:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create product_outcomes + product_events with their indexes."""
    op.create_table(
        "product_outcomes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("workflow_id", sa.String(length=255), nullable=True),
        sa.Column(
            "result_type",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "domain",
            sa.String(length=64),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("execution_mode", sa.String(length=16), nullable=False, server_default="pipeline"),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("device_class", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("locale", sa.String(length=10), nullable=False, server_default="fr"),
        sa.Column(
            "state",
            sa.String(length=16),
            nullable=False,
            server_default="produced",
        ),
        sa.Column("evidence_level", sa.String(length=2), nullable=False, server_default="E3"),
        sa.Column("produced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_pass", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("corrected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reverted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("turn_count", sa.Integer(), nullable=True),
        sa.Column(
            "cost_eur",
            sa.Numeric(10, 6),
            nullable=True,
        ),
        sa.Column("app_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", name="product_outcomes_run_id_key"),
    )
    op.create_index("ix_product_outcomes_user_id", "product_outcomes", ["user_id"])
    op.create_index("ix_product_outcomes_state", "product_outcomes", ["state"])
    op.create_index(
        "ix_product_outcomes_user_produced", "product_outcomes", ["user_id", "produced_at"]
    )
    op.create_index(
        "ix_product_outcomes_evidence_validated",
        "product_outcomes",
        ["evidence_level", "validated_at"],
    )
    op.create_index(
        "ix_product_outcomes_state_produced", "product_outcomes", ["state", "produced_at"]
    )

    op.create_table(
        "product_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.String(length=255), nullable=True),
        sa.Column(
            "event_type",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column("channel", sa.String(length=16), nullable=False, server_default="unknown"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "payload",
            JSONB,
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_product_events_user_id", "product_events", ["user_id"])
    op.create_index("ix_product_events_run_id", "product_events", ["run_id"])
    op.create_index("ix_product_events_event_type", "product_events", ["event_type"])
    op.create_index(
        "ix_product_events_user_occurred", "product_events", ["user_id", "occurred_at"]
    )
    op.create_index(
        "ix_product_events_type_occurred", "product_events", ["event_type", "occurred_at"]
    )


def downgrade() -> None:
    """Drop product analytics tables (indexes fall with the tables)."""
    op.drop_table("product_events")
    op.drop_table("product_outcomes")
