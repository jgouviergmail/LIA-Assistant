"""add_user_home_location

Revision ID: add_user_home_location_001
Revises: add_personalities_001
Create Date: 2025-12-12 00:00:00.000000

Adds home_location_encrypted field to users table for location-aware features.
The field stores Fernet-encrypted JSON containing:
- address: Human-readable address string
- lat: Latitude coordinate
- lon: Longitude coordinate
- place_id: Optional Google Place ID

Requires Google Places connector to be active for configuration.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_user_home_location_001"
down_revision: str | None = "add_personalities_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add home_location_encrypted column to users table.

    - Column: home_location_encrypted (Text)
    - Nullable: True (optional feature)
    - Content: Fernet-encrypted JSON {address, lat, lon, place_id}
    - Use case: Location-aware queries (weather, places) with implicit location injection
    - Privacy: Encrypted at rest using Fernet symmetric encryption
    """
    op.add_column(
        "users",
        sa.Column(
            "home_location_encrypted",
            sa.Text(),
            nullable=True,
            comment="Fernet-encrypted home location JSON: {address, lat, lon, place_id}",
        ),
    )


def downgrade() -> None:
    """
    Remove home_location_encrypted column from users table.
    """
    op.drop_column("users", "home_location_encrypted")
