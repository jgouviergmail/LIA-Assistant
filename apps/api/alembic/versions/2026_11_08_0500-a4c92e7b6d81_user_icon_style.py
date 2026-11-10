"""Persist the account's icon style, with Fluent Color for every account.

Revision ID: a4c92e7b6d81
Revises: c2b92b47d7f5
Create Date: 2026-11-08 05:00:00.000000

The constant server default populates existing rows as the column is added,
and applies to future inserts, including paths outside the ORM. No previous
icon-style preference exists to preserve. Values are frozen here so replaying
this migration never depends on a later application default.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4c92e7b6d81"
down_revision: str | Sequence[str] | None = "c2b92b47d7f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONSTRAINT = "ck_users_icon_style"


def upgrade() -> None:
    """Give existing and new accounts Fluent Color, bounded by the three styles."""
    op.add_column(
        "users",
        sa.Column(
            "icon_style",
            sa.String(length=20),
            nullable=False,
            server_default="fluent",
            comment="Interface icon style: lucide, fluent, flex.",
        ),
    )
    op.create_check_constraint(_CONSTRAINT, "users", "icon_style IN ('lucide', 'fluent', 'flex')")


def downgrade() -> None:
    """Remove the icon preference; all other account preferences remain intact."""
    op.drop_constraint(_CONSTRAINT, "users", type_="check")
    op.drop_column("users", "icon_style")
