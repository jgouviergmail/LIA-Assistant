"""Drop users.sub_agents_enabled column (ADR-083 Phase 2 Task 4 — Option B).

Revision ID: phase_2_cleanup_002
Revises: phase_2_cleanup_001
Create Date: 2026-05-13

The per-user `sub_agents_enabled` toggle was removed (Option B). Delegation
to the ephemeral ReAct sub-agent is now gated only by the global
SUB_AGENTS_ENABLED feature flag (envvar). `SubAgentsSettings.tsx` (orphan
frontend component), the `PATCH /auth/me/sub-agents-preference` endpoint,
its schemas/APIMessage, the ORM column on `users`, and the preference check
in `delegate_to_sub_agent_tool` were all removed.

Downgrade re-creates the column (mirrors sub_agents_003) — data is NOT
restored (the column was a simple opt-out, default true; no business
information lost).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "phase_2_cleanup_002"
down_revision: str | None = "phase_2_cleanup_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop users.sub_agents_enabled column."""
    op.drop_column("users", "sub_agents_enabled")


def downgrade() -> None:
    """Recreate users.sub_agents_enabled column (default true)."""
    op.add_column(
        "users",
        sa.Column(
            "sub_agents_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
            comment="User preference for sub-agent delegation (true = enabled)",
        ),
    )
