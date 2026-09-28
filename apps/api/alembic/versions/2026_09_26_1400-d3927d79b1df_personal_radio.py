"""The personal radio's durable state (ADR-324).

Revision ID: d3927d79b1df
Revises: 3e625df0094a
Create Date: 2026-09-26 14:00:00.000000

Three tables, all new — nothing existing is read or rewritten:

- ``radio_preferences``: one row per listener, their settings as JSONB, the
  personality the station speaks with (``SET NULL``: the station falls back to
  the listener's own when that personality goes) and when they last listened
  (the newsroom reads only for recent listeners);
- ``radio_feeds``: the feeds the newsroom reads — the shipped catalogue (no
  owner, synchronised by the collector at its first pass) and the sites a
  listener adds (``CASCADE`` from their account; the account purge deletes
  them explicitly, since the deletion scrubs the users row);
- ``radio_news_items``: the stories read from them, unique per feed and item
  key, with their full text when the outlet allows it (``CASCADE`` from their
  feed: a removed site takes its stories).

The downgrade drops the three tables: the settings a listener chose and the
sites they added are lost with it, the stories are a cache the collector
rebuilds.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d3927d79b1df"
down_revision: str | None = "3e625df0094a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PREFERENCES_COMMENT = (
    "The listener's radio settings (RadioPreferences without the personality); "
    "read field by field, so a row older than a field reads as its default."
)
_PERSONALITY_ID_COMMENT = "The personality the station speaks with; NULL = the listener's own."
_LAST_LISTENED_AT_COMMENT = (
    "When the listener last started a session; the newsroom reads only for recent listeners."
)
_OWNER_ID_COMMENT = "The listener who added this site; NULL = a feed of the shipped catalogue."
_OUTLET_COMMENT = "The outlet as the station names it (the catalogue's, or the site's title)."
_LANGUAGE_COMMENT = "The feed's language (catalogue), or the one the site declares; NULL = unknown."
_CATEGORY_COMMENT = "The catalogue's kind of journalism; NULL for a listener's own site."
_FULL_TEXT_COMMENT = "Whether the articles' full text may be fetched (the outlet allows it)."
_LAST_STATUS_COMMENT = "How the last reading ended (a bounded vocabulary: ok, not_modified, ...)."
_FAILURES_COMMENT = "Readings failed in a row; the back-off grows with it."
_ITEM_KEY_COMMENT = "The item's identity within its feed (guid, else link)."
_FINGERPRINT_COMMENT = "The same story across outlets (a normalised title)."
_TEXT_STATE_COMMENT = "none | pending | ready | unavailable — where the full text stands."


def upgrade() -> None:
    """Create the three tables and their indexes."""
    op.create_table(
        "radio_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "preferences",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
            comment=_PREFERENCES_COMMENT,
        ),
        sa.Column(
            "personality_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("personalities.id", ondelete="SET NULL"),
            nullable=True,
            comment=_PERSONALITY_ID_COMMENT,
        ),
        sa.Column(
            "last_listened_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=_LAST_LISTENED_AT_COMMENT,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_radio_preferences_user"),
    )

    op.create_table(
        "radio_feeds",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
            comment=_OWNER_ID_COMMENT,
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("outlet", sa.String(160), nullable=False, comment=_OUTLET_COMMENT),
        sa.Column("language", sa.String(16), nullable=True, comment=_LANGUAGE_COMMENT),
        sa.Column("category", sa.String(32), nullable=True, comment=_CATEGORY_COMMENT),
        sa.Column(
            "full_text",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment=_FULL_TEXT_COMMENT,
        ),
        sa.Column("etag", sa.String(512), nullable=True),
        sa.Column("last_modified", sa.String(128), nullable=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(32), nullable=True, comment=_LAST_STATUS_COMMENT),
        sa.Column(
            "failures",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment=_FAILURES_COMMENT,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_radio_feeds_catalogue_url",
        "radio_feeds",
        ["url"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NULL"),
    )
    op.create_index(
        "uq_radio_feeds_owner_url",
        "radio_feeds",
        ["owner_id", "url"],
        unique=True,
        postgresql_where=sa.text("owner_id IS NOT NULL"),
    )

    op.create_table(
        "radio_news_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "feed_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("radio_feeds.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_key", sa.String(512), nullable=False, comment=_ITEM_KEY_COMMENT),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprint", sa.String(200), nullable=False, comment=_FINGERPRINT_COMMENT),
        sa.Column("full_text", sa.Text(), nullable=True),
        sa.Column(
            "text_state",
            sa.String(16),
            nullable=False,
            server_default=sa.text("'none'"),
            comment=_TEXT_STATE_COMMENT,
        ),
        sa.Column("text_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "uq_radio_news_items_feed_key",
        "radio_news_items",
        ["feed_id", "item_key"],
        unique=True,
    )
    op.create_index(
        "ix_radio_news_items_published",
        "radio_news_items",
        [sa.text("published_at DESC")],
    )
    op.create_index(
        "ix_radio_news_items_text_pending",
        "radio_news_items",
        [sa.text("published_at DESC")],
        postgresql_where=sa.text("text_state = 'pending'"),
    )


def downgrade() -> None:
    """Drop the three tables (a listener's settings and added sites go with them)."""
    op.drop_index("ix_radio_news_items_text_pending", table_name="radio_news_items")
    op.drop_index("ix_radio_news_items_published", table_name="radio_news_items")
    op.drop_index("uq_radio_news_items_feed_key", table_name="radio_news_items")
    op.drop_table("radio_news_items")
    op.drop_index("uq_radio_feeds_owner_url", table_name="radio_feeds")
    op.drop_index("uq_radio_feeds_catalogue_url", table_name="radio_feeds")
    op.drop_table("radio_feeds")
    op.drop_table("radio_preferences")
