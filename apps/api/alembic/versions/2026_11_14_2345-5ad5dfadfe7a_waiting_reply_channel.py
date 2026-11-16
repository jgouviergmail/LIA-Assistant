"""A message written on Telegram while LIA works waits too, and is answered there.

Revision ID: 5ad5dfadfe7a
Revises: 7fb09b785088

ADR-384 kept the words a person writes while LIA works; Telegram still answered
« busy » and dropped them (lot 34 of the channel programme). A message written
on a channel now waits like the app's, and its answer must go back to the chat
the person waits in: ``waiting_messages.reply_channel`` names the channel some
of the words were written on (NULL: the app). Once set, it stays set while the
message waits — words added from the app do not take the answer away from that
chat. Nullable, no backfill: every row before was the app's.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5ad5dfadfe7a"
down_revision: str | Sequence[str] | None = "7fb09b785088"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "waiting_messages"
_CHECK = "ck_waiting_message_reply_channel"


def upgrade() -> None:
    """Name the channel a waiting message is answered on."""
    op.add_column(
        _TABLE,
        sa.Column(
            "reply_channel",
            sa.String(length=20),
            nullable=True,
            comment=(
                "The external channel some of the words were written on, where the answer "
                "goes; NULL: the app. Once set it stays set while the message waits."
            ),
        ),
    )
    op.create_check_constraint(
        _CHECK, _TABLE, "reply_channel IS NULL OR reply_channel IN ('telegram')"
    )


def downgrade() -> None:
    """Forget the channel: every waiting message is answered in the app again."""
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.drop_column(_TABLE, "reply_channel")
