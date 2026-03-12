"""Add domain_description and tool_embeddings_cache to user_mcp_servers.

Revision ID: user_mcp_servers_002
Revises: user_mcp_servers_001
Create Date: 2026-03-01

New columns for first-class MCP pipeline integration:
- domain_description: User-provided domain description for query routing (LLM domain detection)
- tool_embeddings_cache: Pre-computed E5 embeddings for semantic tool scoring

Phase: evolution F2.1 — MCP Per-User (pipeline integration)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "user_mcp_servers_002"
down_revision: str | None = "user_mcp_servers_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add domain_description and tool_embeddings_cache columns."""
    op.add_column(
        "user_mcp_servers",
        sa.Column(
            "domain_description",
            sa.Text(),
            nullable=True,
            comment="User-provided domain description for query routing (shown to LLM)",
        ),
    )
    op.add_column(
        "user_mcp_servers",
        sa.Column(
            "tool_embeddings_cache",
            postgresql.JSONB(),
            nullable=True,
            comment="Pre-computed E5 embeddings for discovered tools (computed at registration)",
        ),
    )


def downgrade() -> None:
    """Remove domain_description and tool_embeddings_cache columns."""
    op.drop_column("user_mcp_servers", "tool_embeddings_cache")
    op.drop_column("user_mcp_servers", "domain_description")
