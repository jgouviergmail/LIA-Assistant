"""add_connector_preferences

Revision ID: connector_preferences_001
Revises: plan_approvals_001
Create Date: 2025-11-28 00:00:00.000000

Adds preferences_encrypted column to connectors table for storing
user-specific connector preferences (e.g., default calendar name,
default task list name).

Security:
- Preferences are encrypted using Fernet (same as credentials_encrypted)
- Values are sanitized before encryption to prevent prompt injection

Use Cases:
- Google Calendar: default_calendar_name
- Google Tasks: default_task_list_name
- Future: extensible for other connector types
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "connector_preferences_001"
down_revision: str | None = "plan_approvals_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Add preferences_encrypted column to connectors table.

    - Column: preferences_encrypted (Text)
    - Nullable: True (not all connectors have preferences)
    - Contains: Fernet-encrypted JSON with connector-specific preferences
    """
    op.add_column(
        "connectors",
        sa.Column(
            "preferences_encrypted",
            sa.Text(),
            nullable=True,
            comment="Encrypted user preferences (JSON): calendar names, task lists, etc.",
        ),
    )


def downgrade() -> None:
    """
    Remove preferences_encrypted column from connectors table.
    """
    op.drop_column("connectors", "preferences_encrypted")
