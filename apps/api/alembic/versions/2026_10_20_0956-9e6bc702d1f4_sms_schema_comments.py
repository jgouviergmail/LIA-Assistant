"""Reconcile SMS column comments required by the structural schema contract.

Revision ID: 9e6bc702d1f4
Revises: 3fd106ace921
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9e6bc702d1f4"
down_revision: str | None = "3fd106ace921"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "sms_messages",
        "logical_bytes",
        existing_type=sa.BigInteger(),
        comment="UTF-8 content plus binary blind terms; not physical disk size.",
        existing_nullable=False,
    )
    op.alter_column(
        "users",
        "ingestion_key_encrypted",
        existing_type=sa.Text(),
        comment="Wrapped tenant HMAC key; never exported or projected to clients.",
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "sms_preferences",
        existing_type=postgresql.JSONB(),
        comment="Ingestion/assistant/push consent; never sender identifiers.",
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "sms_preferences",
        existing_type=postgresql.JSONB(),
        comment=None,
        existing_nullable=True,
    )
    op.alter_column(
        "users",
        "ingestion_key_encrypted",
        existing_type=sa.Text(),
        comment=None,
        existing_nullable=True,
    )
    op.alter_column(
        "sms_messages",
        "logical_bytes",
        existing_type=sa.BigInteger(),
        comment=None,
        existing_nullable=False,
    )
