"""Persist the account's automatic light/absolute-black civil-time schedule.

Revision ID: b74d02e6a193
Revises: 5f4ae86b5823
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b74d02e6a193"
down_revision: str | Sequence[str] | None = "5f4ae86b5823"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add valid defaults without changing existing manual display preferences."""
    op.alter_column(
        "users",
        "theme",
        existing_type=sa.String(length=20),
        comment="Display preference: light, dark, system, oled or auto (account civil-time schedule).",
    )
    op.add_column(
        "users",
        sa.Column(
            "theme_light_start_minute", sa.SmallInteger(), nullable=False, server_default="420"
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "theme_dark_start_minute", sa.SmallInteger(), nullable=False, server_default="1200"
        ),
    )
    op.create_check_constraint(
        "ck_users_theme_light_minute", "users", "theme_light_start_minute BETWEEN 0 AND 1439"
    )
    op.create_check_constraint(
        "ck_users_theme_dark_minute", "users", "theme_dark_start_minute BETWEEN 0 AND 1439"
    )
    op.create_check_constraint(
        "ck_users_theme_distinct_boundaries",
        "users",
        "theme_light_start_minute <> theme_dark_start_minute",
    )


def downgrade() -> None:
    """Keep a legal legacy preference when rolling back the schedule feature."""
    op.alter_column(
        "users",
        "theme",
        existing_type=sa.String(length=20),
        comment="User display mode preference: 'light', 'dark', or 'system' (follow OS).",
    )
    op.execute("UPDATE users SET theme = 'system' WHERE theme = 'auto'")
    op.drop_constraint("ck_users_theme_distinct_boundaries", "users", type_="check")
    op.drop_constraint("ck_users_theme_dark_minute", "users", type_="check")
    op.drop_constraint("ck_users_theme_light_minute", "users", type_="check")
    op.drop_column("users", "theme_dark_start_minute")
    op.drop_column("users", "theme_light_start_minute")
