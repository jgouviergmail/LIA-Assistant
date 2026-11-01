"""A routine may pre-approve MCP servers (spec 2026-10-29 D9).

Revision ID: c7e2a9f4b1d3
Revises: b2a59e675271
Create Date: 2026-10-30 14:00:00.000000

A routine runs with nobody to ask, so the effect gate refuses its ``confirm``
calls (ADR-263). The routine's form may now tick the MCP servers whose
confirmations a run gives itself; this column holds their keys. Nullable with no
default: every existing routine pre-approves nothing, exactly as before. The
downgrade drops the column — the ticks are lost, and so is nothing else.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c7e2a9f4b1d3"
down_revision: str | None = "b2a59e675271"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Mirrored EXACTLY by the model's ``comment=`` (the replay check compares them).
_COMMENT = "MCP server keys a run may confirm for itself (routine form only). NULL = none."


def upgrade() -> None:
    """Add the routine's pre-approved MCP servers; NULL pre-approves nothing."""
    op.add_column(
        "scheduled_actions",
        sa.Column(
            "mcp_preapproved_servers",
            postgresql.JSONB(),
            nullable=True,
            comment=_COMMENT,
        ),
    )


def downgrade() -> None:
    """Drop the column; every routine pre-approves nothing again."""
    op.drop_column("scheduled_actions", "mcp_preapproved_servers")
