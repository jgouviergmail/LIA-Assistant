"""Google push channel registry (lot H, 2026-08).

One row per live Google watch (Calendar events.watch, Drive changes.watch,
Gmail users.watch): owner, watched target, the secrets Google echoes back,
expiry (driving the renewal job), the Drive changes baseline, and the Gmail
historyId dedup ledger. Unique per (user, provider, target); channel_id is
globally unique — it is the notification lookup key.

Revision ID: 9b0c1d2e3f4a
Revises: 8a9b0c1d2e3f
Create Date: 2026-08-21 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "9b0c1d2e3f4a"
down_revision: str | None = "8a9b0c1d2e3f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the webhook_channels table."""
    op.create_table(
        "webhook_channels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "provider",
            sa.String(length=30),
            nullable=False,
            comment="google_calendar | google_drive | google_gmail",
        ),
        sa.Column(
            "watch_target",
            sa.String(length=255),
            nullable=False,
            comment="calendar id, 'changes' (drive) or the mailbox address (gmail)",
        ),
        sa.Column(
            "channel_id",
            sa.String(length=64),
            nullable=False,
            comment="Our channel identifier, echoed by Google in X-Goog-Channel-ID",
        ),
        sa.Column(
            "resource_id",
            sa.String(length=255),
            nullable=True,
            comment="Google's opaque resource id (needed to stop the channel)",
        ),
        sa.Column(
            "token",
            sa.String(length=128),
            nullable=False,
            comment="Opaque secret echoed by Google in X-Goog-Channel-Token",
        ),
        sa.Column(
            "expiration",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Channel expiry (UTC) — renewal recreates before this instant",
        ),
        sa.Column(
            "page_token",
            sa.String(length=64),
            nullable=True,
            comment="Drive only: the changes baseline pageToken of the watch",
        ),
        sa.Column(
            "last_history_id",
            sa.BigInteger(),
            nullable=True,
            comment="Gmail only: highest historyId seen (Pub/Sub dedup ledger)",
        ),
        sa.Column(
            "last_notification_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last accepted notification (freshness/monitoring signal)",
        ),
        sa.UniqueConstraint(
            "user_id", "provider", "watch_target", name="uq_webhook_channel_target"
        ),
    )
    op.create_index("ix_webhook_channels_user_id", "webhook_channels", ["user_id"])
    op.create_index(
        "ix_webhook_channels_channel_id", "webhook_channels", ["channel_id"], unique=True
    )
    op.create_index("ix_webhook_channels_expiration", "webhook_channels", ["expiration"])


def downgrade() -> None:
    """Drop the webhook_channels table (live channels expire on their own)."""
    op.drop_index("ix_webhook_channels_expiration", table_name="webhook_channels")
    op.drop_index("ix_webhook_channels_channel_id", table_name="webhook_channels")
    op.drop_index("ix_webhook_channels_user_id", table_name="webhook_channels")
    op.drop_table("webhook_channels")
