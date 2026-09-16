"""The phone domains a person switched off for their own calls (phone-as-a-channel, lot 8).

One JSONB column on ``users`` holding the DISABLED set — a domain the phone
starts offering later is on by default, because parity with the chat is the
rule and the switch is the exception. Vocabulary:
``domains/shared/phone_domains.PHONE_DOMAINS``.

Revision ID: c4d9f1a3e5b7
Revises: b3c8e0f2d4a6
Create Date: 2026-09-16 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4d9f1a3e5b7"
down_revision: str | None = "b3c8e0f2d4a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = "Phone domains switched off for owner calls (the disabled set)."


def upgrade() -> None:
    """Add the disabled-domains column, empty for everyone."""
    op.add_column(
        "users",
        sa.Column(
            "phone_disabled_domains",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment=_COMMENT,
        ),
    )


def downgrade() -> None:
    """Drop the column."""
    op.drop_column("users", "phone_disabled_domains")
