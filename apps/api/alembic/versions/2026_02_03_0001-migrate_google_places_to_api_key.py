"""Migrate Google Places connectors from OAuth to API Key.

Revision ID: migrate_places_api_key_001
Revises: add_voice_mode_enabled_001
Create Date: 2026-02-03

Migration Strategy:
1. Convert existing ACTIVE and ERROR OAuth connectors to "enabled" state
2. Clear OAuth credentials (no longer needed - uses global API key)
3. Update connector_metadata to mark auth_type as 'global_api_key'
4. Delete INACTIVE and REVOKED connectors (user can re-enable via toggle)

This migration supports the transition from per-user OAuth authentication
to a global API key for Google Places, simplifying the user experience.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "migrate_places_api_key_001"
down_revision: str | None = "add_voice_mode_enabled_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Migrate Google Places connectors to API key based authentication.

    - ACTIVE connectors: Remain ACTIVE, clear OAuth credentials
    - ERROR connectors: Convert to ACTIVE (OAuth errors no longer apply)
    - INACTIVE/REVOKED: Delete (user can re-enable via simple toggle)
    """
    conn = op.get_bind()

    # Update ACTIVE and ERROR connectors to use global API key
    # Clear credentials and update metadata
    conn.execute(
        sa.text("""
            UPDATE connectors
            SET
                credentials_encrypted = '{}',
                metadata = COALESCE(metadata, '{}'::jsonb) || '{"auth_type": "global_api_key"}'::jsonb,
                status = 'active'
            WHERE connector_type = 'google_places'
            AND status IN ('active', 'error')
        """)
    )

    # Delete INACTIVE and REVOKED connectors
    # Users can simply re-enable via toggle in settings
    conn.execute(
        sa.text("""
            DELETE FROM connectors
            WHERE connector_type = 'google_places'
            AND status IN ('inactive', 'revoked')
        """)
    )


def downgrade() -> None:
    """
    Mark connectors as ERROR since OAuth tokens are lost.

    After downgrade, users will need to reconnect via OAuth flow.
    """
    conn = op.get_bind()

    conn.execute(
        sa.text("""
            UPDATE connectors
            SET
                status = 'error',
                metadata = COALESCE(metadata, '{}'::jsonb) || '{"downgrade_note": "Requires OAuth reconnection after downgrade"}'::jsonb
            WHERE connector_type = 'google_places'
        """)
    )
