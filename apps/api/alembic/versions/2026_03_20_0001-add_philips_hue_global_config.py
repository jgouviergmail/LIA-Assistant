"""Add Philips Hue to connector_global_config.

Seeds the global config table with the Philips Hue connector type,
enabled by default.

Revision ID: hue_global_config_001
Revises: journals_002
Create Date: 2026-03-20
"""

from alembic import op

# revision identifiers
revision: str = "hue_global_config_001"
down_revision: str | None = "journals_002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Philips Hue to connector_global_config."""
    # Use enum .name (PHILIPS_HUE) not .value (philips_hue) — SQLAlchemy Enum(native_enum=False)
    # stores member names by default. All other connector_type values in DB use uppercase names.
    op.execute("""
        INSERT INTO connector_global_config (id, connector_type, is_enabled, disabled_reason)
        VALUES (gen_random_uuid(), 'PHILIPS_HUE', true, NULL)
        ON CONFLICT (connector_type) DO NOTHING
    """)
    # Fix any existing rows with lowercase value (from previous buggy migration)
    op.execute("""
        UPDATE connector_global_config
        SET connector_type = 'PHILIPS_HUE'
        WHERE connector_type = 'philips_hue'
    """)


def downgrade() -> None:
    """Remove Philips Hue from connector_global_config."""
    op.execute("DELETE FROM connector_global_config WHERE connector_type = 'PHILIPS_HUE'")
