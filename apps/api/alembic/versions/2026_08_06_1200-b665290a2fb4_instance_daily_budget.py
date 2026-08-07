"""Instance-wide daily spend ledger (live-demonstrator programme, lot 1).

One row per UTC day for the WHOLE instance: the only ceiling that holds
when every visitor gets their own account. Written exclusively through an
atomic UPSERT with column arithmetic, so concurrent runs cannot lose spend.

Revision ID: b665290a2fb4
Revises: c3d4e5f6a7b8
Create Date: 2026-08-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b665290a2fb4"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ledger with its unique day key."""
    op.create_table(
        "instance_daily_budget",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("utc_day", sa.Date(), nullable=False),
        sa.Column(
            "spent_cost_eur",
            sa.Numeric(12, 6),
            nullable=False,
            server_default="0",
        ),
        sa.Column("run_count", sa.BigInteger(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint("utc_day", name="uq_instance_daily_budget_utc_day"),
        sa.CheckConstraint(
            "spent_cost_eur >= 0 AND run_count >= 0",
            name="ck_instance_daily_budget_non_negative",
        ),
    )
    op.create_index(
        "ix_instance_daily_budget_utc_day", "instance_daily_budget", ["utc_day"]
    )


def downgrade() -> None:
    """Drop the ledger (spend history is operational, never user data)."""
    op.drop_index("ix_instance_daily_budget_utc_day", table_name="instance_daily_budget")
    op.drop_table("instance_daily_budget")
