"""Offline MCP authentication requirements and exact retained transfer byte counts.

Revision ID: b05f41e932c7
Revises: a94e30f821b6
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "b05f41e932c7"
down_revision: str | None = "a94e30f821b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "peer_capability_transfers",
        sa.Column("payload_bytes", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "user_mcp_servers",
        sa.Column("required_header_name", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_mcp_servers", "required_header_name")
    op.drop_column("peer_capability_transfers", "payload_bytes")
