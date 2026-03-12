"""Create user_mcp_servers table.

Revision ID: user_mcp_servers_001
Revises: scheduled_actions_001
Create Date: 2026-02-28

Per-user MCP server configurations with encrypted credentials.
Only streamable_http transport is allowed (no stdio for security).
Supports none, api_key, bearer, and oauth2 authentication types.

Phase: evolution F2.1 — MCP Per-User
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "user_mcp_servers_001"
down_revision: str | None = "scheduled_actions_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create user_mcp_servers table with indexes and constraints."""
    op.create_table(
        "user_mcp_servers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "name",
            sa.String(100),
            nullable=False,
            comment="User-facing server name (unique per user)",
        ),
        sa.Column(
            "url",
            sa.String(2048),
            nullable=False,
            comment="Streamable HTTP endpoint URL",
        ),
        sa.Column(
            "auth_type",
            sa.String(20),
            nullable=False,
            server_default="none",
            comment="Authentication type: none, api_key, bearer, oauth2",
        ),
        sa.Column(
            "credentials_encrypted",
            sa.Text(),
            nullable=True,
            comment="Fernet-encrypted JSON credentials (NEVER exposed via API)",
        ),
        sa.Column(
            "oauth_metadata",
            postgresql.JSONB(),
            nullable=True,
            comment="Cached OAuth authorization server metadata (RFC 8414/9728)",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="active",
            comment="Server connection status: active, inactive, auth_required, error",
        ),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="User toggle for enabling/disabling this server",
        ),
        sa.Column(
            "timeout_seconds",
            sa.SmallInteger(),
            nullable=False,
            server_default="30",
            comment="Timeout for tool calls on this server (seconds)",
        ),
        sa.Column(
            "hitl_required",
            sa.Boolean(),
            nullable=True,
            comment="Per-server HITL override. NULL = inherit global MCP_HITL_REQUIRED",
        ),
        sa.Column(
            "discovered_tools_cache",
            postgresql.JSONB(),
            nullable=True,
            comment="Cached list_tools() result for fast startup",
        ),
        sa.Column(
            "last_connected_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful connection timestamp",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="Last connection/execution error message",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Standard index on user_id
    op.create_index(
        "ix_user_mcp_servers_user_id",
        "user_mcp_servers",
        ["user_id"],
    )

    # Unique constraint: one server name per user
    op.create_unique_constraint(
        "uq_user_mcp_server_name",
        "user_mcp_servers",
        ["user_id", "name"],
    )

    # Partial index: enabled + active servers per user (hot path for chat)
    op.create_index(
        "ix_user_mcp_servers_user_enabled",
        "user_mcp_servers",
        ["user_id"],
        postgresql_where=sa.text("is_enabled = true AND status = 'active'"),
    )


def downgrade() -> None:
    """Drop user_mcp_servers table."""
    op.drop_index(
        "ix_user_mcp_servers_user_enabled", table_name="user_mcp_servers"
    )
    op.drop_constraint(
        "uq_user_mcp_server_name", "user_mcp_servers", type_="unique"
    )
    op.drop_index(
        "ix_user_mcp_servers_user_id", table_name="user_mcp_servers"
    )
    op.drop_table("user_mcp_servers")
