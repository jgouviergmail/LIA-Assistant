"""Widen connector_type column to VARCHAR(50) for Microsoft connector types.

The column was auto-sized to VARCHAR(15) by SQLAlchemy Enum(native_enum=False)
based on the longest enum value at the time ('google_calendar' = 15 chars).
Microsoft connector types like 'microsoft_contacts' (20 chars) exceed this limit.

Revision ID: widen_connector_type_001
Revises: add_attachments_001
Create Date: 2026-03-10 00:01:00.000000

Phase: Microsoft 365 connectors integration
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "widen_connector_type_001"
down_revision: str | None = "add_attachments_001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column(
        "connectors",
        "connector_type",
        existing_type=sa.VARCHAR(length=15),
        type_=sa.String(length=50),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "connectors",
        "connector_type",
        existing_type=sa.String(length=50),
        type_=sa.VARCHAR(length=15),
        existing_nullable=False,
    )
