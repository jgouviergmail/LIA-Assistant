"""Add system_settings table.

Revision ID: add_system_settings_001
Revises: add_user_theme_prefs_001
Create Date: 2026-01-16

This migration adds the system_settings table for application-wide
configuration managed by administrators.

- key: Setting identifier (enum stored as string)
- value: Setting value (string)
- updated_by: Admin user who last changed the setting
- change_reason: Optional reason for the change

Initial use case: voice_tts_mode setting for Standard/HD voice quality toggle.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "add_system_settings_001"
down_revision: str | None = "add_user_theme_prefs_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add system_settings table for application-wide configuration.
    """
    op.create_table(
        "system_settings",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("key", name="uq_system_settings_key"),
    )

    # Create index on key for fast lookup
    op.create_index(
        "ix_system_settings_key",
        "system_settings",
        ["key"],
    )

    # Create index on updated_by for admin audit queries
    op.create_index(
        "ix_system_settings_updated_by",
        "system_settings",
        ["updated_by"],
    )


def downgrade() -> None:
    """
    Remove system_settings table.
    """
    op.drop_index("ix_system_settings_updated_by", table_name="system_settings")
    op.drop_index("ix_system_settings_key", table_name="system_settings")
    op.drop_table("system_settings")
