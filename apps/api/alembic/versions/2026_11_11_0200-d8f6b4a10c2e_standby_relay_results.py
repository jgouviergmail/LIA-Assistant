"""Settle a standby relay and its closing card in one transaction.

Revision ID: d8f6b4a10c2e
Revises: a5810c2d4e61
"""

from alembic import op
import sqlalchemy as sa

revision = "d8f6b4a10c2e"
down_revision = "a5810c2d4e61"
branch_labels = None
depends_on = None

_TABLE = "conversation_reservation_work"
_CHECK = "ck_conversation_reservation_work_standby_recap"


def upgrade() -> None:
    """Keep an encrypted recap until the card commits and a marker after consumption."""
    op.add_column(
        _TABLE,
        sa.Column("standby_relay_settled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(_TABLE, sa.Column("standby_recap", sa.Text(), nullable=True))
    op.create_check_constraint(
        _CHECK,
        _TABLE,
        "(NOT standby_relay_settled OR purpose = 'relay') "
        "AND (standby_recap IS NULL OR standby_relay_settled)",
    )


def downgrade() -> None:
    """Keep completed cards and refuse to discard a relay or recap in flight."""
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM conversation_reservation_work "
            "WHERE standby_recap IS NOT NULL OR (purpose = 'relay' AND phase <> 'closed'))"
        )
    ):
        raise RuntimeError("Resolve outstanding standby relays before downgrade")
    op.drop_constraint(_CHECK, _TABLE, type_="check")
    op.drop_column(_TABLE, "standby_recap")
    op.drop_column(_TABLE, "standby_relay_settled")
