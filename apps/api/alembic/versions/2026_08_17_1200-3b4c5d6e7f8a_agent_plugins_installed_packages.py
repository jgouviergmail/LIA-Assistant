"""Agent Plugins installed packages + provenance links (ADR-225).

Creates ``user_plugins`` (one row per installed plugin instance per user)
and adds two nullable provenance columns:

- ``skills.plugin_id`` — which plugin installed this skill;
- ``user_mcp_servers.plugin_id`` — which plugin installed this server;
- ``user_mcp_servers.extra_headers`` — fixed non-secret HTTP headers from a
  plugin's mcp.json (§7.2.1, arbitrage C).

Everything is additive and nullable: existing rows keep behaving
byte-for-byte (NULL = manually created, no fixed headers). ``SET NULL`` on
the provenance FK is the safety net — a raw plugin row deletion demotes its
components to ordinary manual ones instead of cascading user data away; the
clean group uninstall (rows + disk trees) is service-driven.

Revision ID: 3b4c5d6e7f8a
Revises: 2a3b4c5d6e7f
Create Date: 2026-08-17 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "3b4c5d6e7f8a"
down_revision: str | None = "2a3b4c5d6e7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create user_plugins and wire the nullable provenance links."""
    op.create_table(
        "user_plugins",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(64),
            nullable=False,
            comment="Plugin name from the manifest (agent-plugins.org §5.5)",
        ),
        sa.Column("version", sa.String(100), nullable=True),
        sa.Column("description", sa.String(1024), nullable=True),
        sa.Column(
            "manifest",
            JSONB,
            nullable=False,
            comment="Full validated plugin.json manifest (unknown fields stripped)",
        ),
        sa.Column(
            "spec_version",
            sa.String(20),
            nullable=False,
            comment="Agent Plugins specification version targeted by the package",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_user_plugins_user_name"),
    )
    op.create_index("ix_user_plugins_user_id", "user_plugins", ["user_id"])

    op.add_column(
        "skills",
        sa.Column(
            "plugin_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user_plugins.id", ondelete="SET NULL"),
            nullable=True,
            comment="Agent Plugins provenance (ADR-225); NULL = manually imported",
        ),
    )
    op.create_index("ix_skills_plugin_id", "skills", ["plugin_id"])

    op.add_column(
        "user_mcp_servers",
        sa.Column(
            "plugin_id",
            UUID(as_uuid=True),
            sa.ForeignKey("user_plugins.id", ondelete="SET NULL"),
            nullable=True,
            comment="Agent Plugins provenance (ADR-225); NULL = manually declared",
        ),
    )
    op.create_index("ix_user_mcp_servers_plugin_id", "user_mcp_servers", ["plugin_id"])
    op.add_column(
        "user_mcp_servers",
        sa.Column(
            "extra_headers",
            JSONB,
            nullable=True,
            comment=(
                "Fixed non-secret HTTP headers from a plugin's mcp.json "
                "(agent-plugins.org §7.2.1); auth headers keep precedence"
            ),
        ),
    )


def downgrade() -> None:
    """Drop the provenance links, then the table (reverse creation order)."""
    op.drop_column("user_mcp_servers", "extra_headers")
    op.drop_index("ix_user_mcp_servers_plugin_id", table_name="user_mcp_servers")
    op.drop_column("user_mcp_servers", "plugin_id")
    op.drop_index("ix_skills_plugin_id", table_name="skills")
    op.drop_column("skills", "plugin_id")
    op.drop_index("ix_user_plugins_user_id", table_name="user_plugins")
    op.drop_table("user_plugins")
