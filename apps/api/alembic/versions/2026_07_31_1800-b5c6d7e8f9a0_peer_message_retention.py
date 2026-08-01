"""peer message content retention

Relayed messages used to be erased at delivery, which left the personal CRM
able to say a message existed but never what it said. They now follow the
contract phone calls already use (ADR-186): the ROW survives forever, the TEXT
is cleared past ``expires_at`` by the peers sweep.

Two texts, never crossed: ``content`` is the sender's own directive,
``delivered_text`` is what the recipient's assistant actually said. Showing
either across would undo the relay.

Rows delivered BEFORE this migration were scrubbed for good — they keep a NULL
text and the UI states it plainly rather than pretending.

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-07-31 18:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b5c6d7e8f9a0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the delivered text and the retention horizon."""
    op.add_column(
        "peer_messages",
        sa.Column(
            "delivered_text",
            sa.Text(),
            nullable=True,
            comment="What the recipient's assistant said; cleared past expires_at.",
        ),
    )
    op.add_column(
        "peer_messages",
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC instant past which both texts are purged (row is kept).",
        ),
    )
    # The column outlives delivery now — its comment said otherwise.
    op.alter_column(
        "peer_messages",
        "content",
        existing_type=sa.Text(),
        existing_nullable=True,
        comment="Sender's own directive text; cleared past expires_at (retention TTL).",
        existing_comment="Sender directive text; set to NULL after successful delivery.",
    )
    # The retention reaper only ever visits expired rows.
    op.create_index(
        "ix_peer_messages_expires_at",
        "peer_messages",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )
    # Give the messages that are still LIVE at migration time an horizon too.
    # `expires_at` is stamped at enqueue from now on, but rows enqueued before
    # this migration have none — and the reaper only visits rows that have one,
    # so their directive would outlive the retention promise forever. The
    # default window is applied from their own enqueue instant, exactly as a
    # fresh row would get; one already past it is purged on the next sweep and
    # cancelled honestly (a message undelivered for a month is not going to
    # arrive). Already-delivered rows were scrubbed by the old code and hold
    # nothing to expire, so they are deliberately left alone.
    op.execute(
        sa.text(
            "UPDATE peer_messages "
            "SET expires_at = created_at + INTERVAL '30 days' "
            "WHERE expires_at IS NULL AND content IS NOT NULL"
        )
    )


def downgrade() -> None:
    """Drop the retention columns and restore the scrub-on-delivery comment."""
    op.drop_index("ix_peer_messages_expires_at", table_name="peer_messages")
    op.alter_column(
        "peer_messages",
        "content",
        existing_type=sa.Text(),
        existing_nullable=True,
        comment="Sender directive text; set to NULL after successful delivery.",
        existing_comment="Sender's own directive text; cleared past expires_at (retention TTL).",
    )
    op.drop_column("peer_messages", "expires_at")
    op.drop_column("peer_messages", "delivered_text")
