"""The person's own phone number, verified (phone-as-a-channel, lot 1).

Three columns on ``users``: the number the person declared, stored Fernet-
encrypted like the home address; when LIA heard them answer it (NULL until
then — an owner call may only skip its confirmation card on a VERIFIED line);
and whether such a call carries the chat's context beyond free/busy.

Revision ID: f1a6c8e4d2b3
Revises: e9b5d7f3a2c4
Create Date: 2026-09-16 09:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a6c8e4d2b3"
down_revision: str | None = "e9b5d7f3a2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NUMBER_COMMENT = "Fernet-encrypted E.164 phone number the person declared as their own."
_VERIFIED_COMMENT = "When LIA heard the person answer the declared number; NULL = unverified."
_RICH_CONTEXT_COMMENT = "Whether an owner call carries the chat's context beyond free/busy."


def upgrade() -> None:
    """Add the three identity columns."""
    op.add_column(
        "users",
        sa.Column("phone_number_encrypted", sa.Text(), nullable=True, comment=_NUMBER_COMMENT),
    )
    op.add_column(
        "users",
        sa.Column(
            "phone_number_verified_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=_VERIFIED_COMMENT,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "phone_rich_context_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
            comment=_RICH_CONTEXT_COMMENT,
        ),
    )


def downgrade() -> None:
    """Drop the three identity columns."""
    op.drop_column("users", "phone_rich_context_enabled")
    op.drop_column("users", "phone_number_verified_at")
    op.drop_column("users", "phone_number_encrypted")
