"""Add iterative_mode to user_mcp_servers.

ADR-062: Enable ReAct iterative mode per user MCP server.
When true, the planner delegates to a ReAct sub-agent that interacts
with the server's tools iteratively for better results on complex tasks.

Revision ID: user_mcp_iterative_mode_001
Revises: journal_injection_tracking_001
Create Date: 2026-03-24
"""

import sqlalchemy as sa
from alembic import op

revision = "user_mcp_iterative_mode_001"
down_revision = "journal_injection_tracking_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_mcp_servers",
        sa.Column(
            "iterative_mode",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_mcp_servers", "iterative_mode")
