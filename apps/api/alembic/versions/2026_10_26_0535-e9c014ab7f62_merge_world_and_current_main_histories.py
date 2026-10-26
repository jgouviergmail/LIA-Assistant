"""Join the current main and world migration histories without replaying either.

Revision ID: e9c014ab7f62
Revises: 8e4c20f65b91, a85f7c4d2e19
"""

from collections.abc import Sequence

revision: str = "e9c014ab7f62"
down_revision: tuple[str, str] = ("8e4c20f65b91", "a85f7c4d2e19")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """The parent revisions own every schema and data change."""


def downgrade() -> None:
    """The merge itself owns no schema or data to reverse."""
