"""Which mandate a call ran under (phone-as-a-channel, lot 2).

One vendor agent now speaks under three mandates — the baked third-party one,
the owner's own call and the number-verification call — so every row names
its kind. ``native_enum=False`` stores the member NAME: the server default is
the NAME too, or every pre-existing row would read as an unknown kind.

Revision ID: a2b7d9f1c3e5
Revises: f1a6c8e4d2b3
Create Date: 2026-09-16 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b7d9f1c3e5"
down_revision: str | None = "f1a6c8e4d2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KIND_COMMENT = "Mandate the call ran under: THIRD_PARTY (baked agent), SELF (owner), VERIFICATION."


def upgrade() -> None:
    """Add the mandate column, every existing row being a third-party call."""
    op.add_column(
        "phone_calls",
        sa.Column(
            "call_kind",
            sa.Enum(
                "THIRD_PARTY",
                "SELF",
                "VERIFICATION",
                name="callkind",
                native_enum=False,
                length=20,
            ),
            nullable=False,
            server_default="THIRD_PARTY",
            comment=_KIND_COMMENT,
        ),
    )


def downgrade() -> None:
    """Drop the mandate column."""
    op.drop_column("phone_calls", "call_kind")
