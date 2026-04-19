"""Add last-known location persistence to users table.

Supports the Phase 3 proactive weather cascade: when the user opts in,
the browser geolocation pushed during chat sessions is persisted
(encrypted, non-historized) so that async jobs (heartbeat) can use
the last-known position when the user is away from home.

Three new columns:
- last_known_location_encrypted: Fernet-encrypted JSON {lat, lon, accuracy}
- last_known_location_updated_at: UTC timestamp of the last update
- weather_use_last_known_location: opt-in flag (default False)

Revision ID: last_known_loc_001
Revises: execution_mode_001
Create Date: 2026-04-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "last_known_loc_001"
down_revision: str | None = "execution_mode_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add three columns to users table for last-known location feature."""
    op.add_column(
        "users",
        sa.Column(
            "last_known_location_encrypted",
            sa.Text(),
            nullable=True,
            comment="Fernet-encrypted last-known location JSON: {lat, lon, accuracy}",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "last_known_location_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC timestamp of the last last-known location update (TTL + throttle).",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "weather_use_last_known_location",
            sa.Boolean(),
            nullable=False,
            server_default="false",
            comment=(
                "Opt-in for using the persisted browser geolocation in proactive "
                "weather notifications when the user is away from home."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the three last-known location columns."""
    op.drop_column("users", "weather_use_last_known_location")
    op.drop_column("users", "last_known_location_updated_at")
    op.drop_column("users", "last_known_location_encrypted")
