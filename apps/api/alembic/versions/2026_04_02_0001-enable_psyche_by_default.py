"""Enable psyche by default for all existing users.

Sets psyche_enabled=true and psyche_display_avatar=true for all users,
and updates the server_default for new users.

Revision ID: psyche_defaults_001
Revises: psyche_traits_001
Create Date: 2026-04-02
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "psyche_defaults_001"
down_revision: str | None = "psyche_traits_001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable psyche for all existing users."""
    # Update existing users
    op.execute("UPDATE users SET psyche_enabled = true WHERE psyche_enabled = false")

    # Update server_default for new users
    op.alter_column("users", "psyche_enabled", server_default="true")


def downgrade() -> None:
    """Revert to psyche disabled by default."""
    op.alter_column("users", "psyche_enabled", server_default="false")
    # Note: does NOT reset existing users — they keep their current preference
