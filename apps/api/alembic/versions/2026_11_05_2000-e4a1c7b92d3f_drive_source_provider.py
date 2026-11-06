"""Which drive a linked folder lives on, and a feed token Graph's length (ADR-369, lot 11).

Revision ID: e4a1c7b92d3f
Revises: 278c441eaae6
Create Date: 2026-11-05 20:00:00.000000

A folder's id means nothing on another drive, so a source now names its drive: every folder linked
so far is Google's, and reads so through the column's default. OneDrive's watch sits beside
Google's in ``webhook_channels``: its delta token is longer than a Drive page token, and the
provider's id of a watch is Graph's subscription there. The downgrade removes OneDrive's channels,
whose tokens fit the former column no more; their subscriptions end on their own.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4a1c7b92d3f"
down_revision: str | None = "278c441eaae6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Mirrored EXACTLY by the models' ``comment=`` (the replay check compares them).
_SOURCE_PROVIDER_COMMENT = "The drive this folder lives on: a ConnectorType value."
_CHANNEL_PROVIDER_COMMENT = "google_calendar | google_drive | google_gmail | microsoft_onedrive"
_RESOURCE_COMMENT = "The provider's id of the watch: Google's resource, Graph's subscription"
_TOKEN_COMMENT = "Opaque secret echoed in X-Goog-Channel-Token, or Graph's clientState"
_PAGE_TOKEN_COMMENT = "Drives only: the changes baseline of the watch (Graph's are long)"


def upgrade() -> None:
    """Name a source's drive, and let a channel hold what Graph answers."""
    op.add_column(
        "rag_drive_sources",
        sa.Column(
            "provider",
            sa.String(length=30),
            nullable=False,
            server_default="google_drive",
            comment=_SOURCE_PROVIDER_COMMENT,
        ),
    )
    op.alter_column(
        "webhook_channels",
        "page_token",
        existing_type=sa.String(length=64),
        type_=sa.String(length=2048),
        existing_nullable=True,
        comment=_PAGE_TOKEN_COMMENT,
        existing_comment="Drive only: the changes baseline pageToken of the watch",
    )
    op.alter_column(
        "webhook_channels",
        "provider",
        existing_type=sa.String(length=30),
        existing_nullable=False,
        comment=_CHANNEL_PROVIDER_COMMENT,
        existing_comment="google_calendar | google_drive | google_gmail",
    )
    op.alter_column(
        "webhook_channels",
        "resource_id",
        existing_type=sa.String(length=255),
        existing_nullable=True,
        comment=_RESOURCE_COMMENT,
        existing_comment="Google's opaque resource id (needed to stop the channel)",
    )
    op.alter_column(
        "webhook_channels",
        "token",
        existing_type=sa.String(length=128),
        existing_nullable=False,
        comment=_TOKEN_COMMENT,
        existing_comment="Opaque secret echoed by Google in X-Goog-Channel-Token",
    )


def downgrade() -> None:
    """Back to Google's channels alone; a OneDrive folder then reads as a Drive one."""
    op.execute("DELETE FROM webhook_channels WHERE provider = 'microsoft_onedrive'")
    op.alter_column(
        "webhook_channels",
        "token",
        existing_type=sa.String(length=128),
        existing_nullable=False,
        comment="Opaque secret echoed by Google in X-Goog-Channel-Token",
        existing_comment=_TOKEN_COMMENT,
    )
    op.alter_column(
        "webhook_channels",
        "resource_id",
        existing_type=sa.String(length=255),
        existing_nullable=True,
        comment="Google's opaque resource id (needed to stop the channel)",
        existing_comment=_RESOURCE_COMMENT,
    )
    op.alter_column(
        "webhook_channels",
        "provider",
        existing_type=sa.String(length=30),
        existing_nullable=False,
        comment="google_calendar | google_drive | google_gmail",
        existing_comment=_CHANNEL_PROVIDER_COMMENT,
    )
    op.alter_column(
        "webhook_channels",
        "page_token",
        existing_type=sa.String(length=2048),
        type_=sa.String(length=64),
        existing_nullable=True,
        comment="Drive only: the changes baseline pageToken of the watch",
        existing_comment=_PAGE_TOKEN_COMMENT,
    )
    op.drop_column("rag_drive_sources", "provider")
