"""T1 approach A: pre-synthesis return inbox (encrypted webhook + reaper state)

Revision ID: d3f1a9c40b52
Revises: c75adcbc2f90
Create Date: 2026-07-14 00:02:41.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3f1a9c40b52"
down_revision: str | None = "c75adcbc2f90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "phone_calls",
        sa.Column(
            "return_status",
            sa.Enum(
                "RECEIVED",
                "SYNTHESIZED",
                "FAILED",
                name="returnsynthesisstatus",
                native_enum=False,
                length=20,
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "phone_calls",
        sa.Column("return_webhook_encrypted", sa.Text(), nullable=True),
    )
    op.add_column(
        "phone_calls",
        sa.Column("return_received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_phone_calls_return_received",
        "phone_calls",
        ["return_received_at"],
        unique=False,
        postgresql_where=sa.text("return_status = 'RECEIVED'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_phone_calls_return_received",
        table_name="phone_calls",
        postgresql_where=sa.text("return_status = 'RECEIVED'"),
    )
    op.drop_column("phone_calls", "return_received_at")
    op.drop_column("phone_calls", "return_webhook_encrypted")
    op.drop_column("phone_calls", "return_status")
