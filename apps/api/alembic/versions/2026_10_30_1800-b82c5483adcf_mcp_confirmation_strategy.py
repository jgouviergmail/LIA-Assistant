"""The person's MCP confirmation strategy and a server's ReAct shape (spec 2026-10-30).

Revision ID: b82c5483adcf
Revises: c7e2a9f4b1d3
Create Date: 2026-10-30 18:00:00.000000

Two nullable columns, NULL meaning « never chosen »: ``users.mcp_hitl_required`` (the
strategy an account's MCP servers inherit, NULL following ``MCP_HITL_REQUIRED``) and
``user_mcp_servers.react_expand_iterative`` (who drives an iterative server in ReAct,
NULL following ``REACT_MCP_EXPAND_ITERATIVE_ENABLED``). Every existing row keeps the
instance defaults, exactly as before. The downgrade drops both — the choices are lost,
and so is nothing else.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b82c5483adcf"
down_revision: str | None = "c7e2a9f4b1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Mirrored EXACTLY by the models' ``comment=`` (the replay check compares them).
_ACCOUNT_COMMENT = (
    "MCP confirmation strategy: true = always ask, false = follow the servers' "
    "declarations; NULL = instance default (MCP_HITL_REQUIRED)."
)
_SHAPE_COMMENT = (
    "ReAct shape of an iterative server: true = the loop drives its tools, "
    "false = its dedicated agent; NULL = instance default."
)


def upgrade() -> None:
    """Add both choices; NULL follows the instance defaults."""
    op.add_column(
        "users",
        sa.Column("mcp_hitl_required", sa.Boolean(), nullable=True, comment=_ACCOUNT_COMMENT),
    )
    op.add_column(
        "user_mcp_servers",
        sa.Column("react_expand_iterative", sa.Boolean(), nullable=True, comment=_SHAPE_COMMENT),
    )


def downgrade() -> None:
    """Drop both choices."""
    op.drop_column("user_mcp_servers", "react_expand_iterative")
    op.drop_column("users", "mcp_hitl_required")
