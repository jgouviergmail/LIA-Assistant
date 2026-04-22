"""Add user-level toggle for Health Metrics assistant integrations.

Adds :attr:`users.health_metrics_agents_enabled` — a boolean flag gating
four integrations at once (conversation agents, Heartbeat source,
journal extractor health context, memory extractor biometric context).

Default ``false`` (opt-in) preserves privacy: until the user toggles the
preference on in Settings → Health Metrics → Assistant, the assistant
never reads their health samples.

Revision ID: health_metrics_004
Revises: health_metrics_003
Create Date: 2026-04-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "health_metrics_004"
down_revision: str | None = "health_metrics_003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the opt-in toggle to the users table."""
    op.add_column(
        "users",
        sa.Column(
            "health_metrics_agents_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment=(
                "Opt-in for Health Metrics integrations with the assistant "
                "(agents, Heartbeat source, journal/memory context). "
                "False by default — user must toggle in Settings."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the opt-in toggle column."""
    op.drop_column("users", "health_metrics_agents_enabled")
