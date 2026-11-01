"""A person's choice for one tool of their MCP server (spec 2026-10-30 D6).

Revision ID: 278c441eaae6
Revises: b82c5483adcf
Create Date: 2026-10-30 23:00:00.000000

One row per (server, tool name): ``always`` (ask before every call) or ``never``
(follow the declaration, unasked), the latter bound to the tool's declaration
fingerprint at the moment it was chosen. The table starts empty: every tool keeps
the levels below, exactly as before. Rows leave with their server (FK cascade). The
downgrade drops the table — the choices are lost, and so is nothing else.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "278c441eaae6"
down_revision: str | None = "b82c5483adcf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Mirrored EXACTLY by the model's ``comment=`` (the replay check compares them).
_SERVER_COMMENT = "The server whose tool this is; the choice leaves with it."
_TOOL_COMMENT = "The tool's raw name, as the server lists it."
_CHOICE_COMMENT = "always: ask before every call; never: follow the declaration, unasked."
_FINGERPRINT_COMMENT = (
    "The tool's annotations and input schema when chosen; another one suspends a never."
)


def upgrade() -> None:
    """Create the per-tool choices; no tool has one yet."""
    op.create_table(
        "user_mcp_tool_choices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "server_id", postgresql.UUID(as_uuid=True), nullable=False, comment=_SERVER_COMMENT
        ),
        sa.Column("tool_name", sa.String(length=255), nullable=False, comment=_TOOL_COMMENT),
        sa.Column("choice", sa.String(length=16), nullable=False, comment=_CHOICE_COMMENT),
        sa.Column(
            "declaration_fingerprint",
            sa.String(length=64),
            nullable=False,
            comment=_FINGERPRINT_COMMENT,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("choice IN ('always', 'never')", name="ck_user_mcp_tool_choices_choice"),
        sa.ForeignKeyConstraint(["server_id"], ["user_mcp_servers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id", "tool_name", name="uq_user_mcp_tool_choices_server_tool"),
    )


def downgrade() -> None:
    """Drop the per-tool choices."""
    op.drop_table("user_mcp_tool_choices")
