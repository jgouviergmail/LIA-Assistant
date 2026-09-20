"""How the person's own phone calls run: Live or Live direct (ADR-301).

Two columns in the voice sessions' mode vocabulary
(``domains/voice_sessions/session.VoiceSessionMode``): ``delegated`` — the
voice hands every request to the chat, which acts in the person's own
conversation, the browser's Live mode on the phone — or ``direct`` — the
voice reads LIA's tools itself and the call is relayed at its end.

- ``users.phone_call_mode`` is the person's CHOICE. Live is the DEFAULT
  (owner decision 2026-09-20): a call that leaves a trace in the conversation
  is the point of the phone as a channel.
- ``phone_calls.call_mode`` is the mode a call actually RAN under, written at
  the dial and read at its closing — a choice flipped mid-call must not close
  a Live call as a direct one. Every call before this revision ran direct.

Revision ID: c9e2a4b6d8f1
Revises: b7d1e3f5a9c2
Create Date: 2026-09-20 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e2a4b6d8f1"
down_revision: str | None = "b7d1e3f5a9c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMENT = "How the person's own calls run: delegated (Live) or direct (Live direct)."
_CALL_COMMENT = "The mode an owner call ran under: delegated (Live) or direct; third-party calls are direct."


def upgrade() -> None:
    """Add the call-mode column, Live for everyone."""
    op.add_column(
        "users",
        sa.Column(
            "phone_call_mode",
            sa.String(length=16),
            nullable=False,
            server_default="delegated",
            comment=_COMMENT,
        ),
    )
    op.add_column(
        "phone_calls",
        sa.Column(
            "call_mode",
            sa.String(length=16),
            nullable=False,
            server_default="direct",
            comment=_CALL_COMMENT,
        ),
    )


def downgrade() -> None:
    """Drop the two columns."""
    op.drop_column("phone_calls", "call_mode")
    op.drop_column("users", "phone_call_mode")
