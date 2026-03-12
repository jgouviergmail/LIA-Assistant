"""Add admin MCP per-user toggle framework.

Revision ID: admin_mcp_001
Revises: heartbeat_002
Create Date: 2026-03-03

Add JSONB column for per-user admin MCP server disable list.
Allows users to toggle off admin-configured MCP servers individually.

Phase: evolution F2.5 — Admin MCP Per-Server Routing & User Toggle
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "admin_mcp_001"
down_revision: str | None = "heartbeat_002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "admin_mcp_disabled_servers",
            JSONB,
            nullable=False,
            server_default="[]",
            comment="List of admin MCP server keys disabled by this user (e.g., ['google_flights'])",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "admin_mcp_disabled_servers")
