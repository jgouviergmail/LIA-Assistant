"""The radio's durable state (ADR-324): a listener's settings and the newsroom.

Sessions live in Redis and their audio on disk, for as long as they air; what
survives them is here:

- ``radio_preferences`` — one row per listener: their settings (a JSONB of
  ``RadioPreferences`` minus the personality, which is a column so the
  personality's deletion can clear it) and when they last listened — the
  newsroom reads only for recent listeners;
- ``radio_feeds`` — the feeds the newsroom reads: the shipped catalogue (no
  owner, synchronised at every pass) and the sites a listener added (their
  owner's rows, purged and exported with them);
- ``radio_news_items`` — the stories read from those feeds, kept for a bounded
  time and their full text when the outlet allows it; a site's stories go with
  the site by FK cascade.

A listener's interests have a row of their own in ``radio_feeds`` (``kind`` =
``interest``, ADR-324 decision 40): the stories a search found for them, filed like
any other so the shortlists, the ledger, the article page and the retention read them
unchanged — and never read by the newsroom, which reads ``source`` rows alone.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.domains.radio.constants import (
    ETAG_MAX_CHARS,
    LANGUAGE_TAG_MAX_CHARS,
    LAST_MODIFIED_MAX_CHARS,
    OUTLET_MAX_CHARS,
    URL_MAX_BYTES,
)
from src.infrastructure.database.models import BaseModel

#: Column comments, shared with the migration — the replay check compares them.
PREFERENCES_COMMENT = (
    "The listener's radio settings (RadioPreferences without the personality); "
    "read field by field, so a row older than a field reads as its default."
)
PERSONALITY_ID_COMMENT = "The personality the station speaks with; NULL = the listener's own."
LAST_LISTENED_AT_COMMENT = (
    "When the listener last started a session; the newsroom reads only for recent listeners."
)
OWNER_ID_COMMENT = "The listener who added this site; NULL = a feed of the shipped catalogue."
OUTLET_COMMENT = "The outlet as the station names it (the catalogue's, or the site's title)."
LANGUAGE_COMMENT = "The feed's language (catalogue), or the one the site declares; NULL = unknown."
PAUSED_COMMENT = "Whether the listener paused their own site: not read, not offered."
FULL_TEXT_COMMENT = "Whether the articles' full text may be fetched (the outlet allows it)."
LAST_STATUS_COMMENT = "How the last reading ended (a bounded vocabulary: ok, not_modified, ...)."
FAILURES_COMMENT = "Readings failed in a row; the back-off grows with it."
ITEM_KEY_COMMENT = "The item's identity within its feed (guid, else link)."
FINGERPRINT_COMMENT = "The same story across outlets (a normalised title)."
TEXT_STATE_COMMENT = "none | pending | ready | unavailable — where the full text stands."
KIND_COMMENT = (
    "source: a feed the newsroom reads (the catalogue's, or a listener's site); "
    "interest: the stories a search found for its owner's interests, never read."
)
ITEM_OUTLET_COMMENT = "The outlet that published the story, when not its feed's; NULL = the feed's."


class TextState(StrEnum):
    """Where an item's full text stands."""

    #: Its feed does not allow the full text to be fetched.
    NONE = "none"
    PENDING = "pending"
    READY = "ready"
    #: Every attempt failed, or the page held no article.
    UNAVAILABLE = "unavailable"


class FeedKind(StrEnum):
    """What a feed row holds."""

    #: A feed the newsroom reads: the catalogue's, or a site a listener added.
    SOURCE = "source"
    #: The stories a search found for its owner's interests (ADR-324 decision 40):
    #: never read by the newsroom; one row per listener (``INTEREST_FEED_URL``).
    INTEREST = "interest"


class RadioPreferencesRow(BaseModel):
    """A listener's radio settings.

    Attributes:
        user_id: Whose settings (one row per account).
        preferences: ``RadioPreferences`` as JSON, without ``personality_id``.
        personality_id: The personality the station speaks with, while it
            exists (``SET NULL``: the station falls back to the listener's own).
        last_listened_at: When they last started a session (``None``: never) —
            the newsroom reads the catalogue while anyone listened recently,
            and a listener's own sites while they did.
    """

    __tablename__ = "radio_preferences"

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
        comment=PREFERENCES_COMMENT,
    )
    personality_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("personalities.id", ondelete="SET NULL"),
        nullable=True,
        comment=PERSONALITY_ID_COMMENT,
    )
    last_listened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment=LAST_LISTENED_AT_COMMENT
    )

    __table_args__ = (UniqueConstraint("user_id", name="uq_radio_preferences_user"),)


class RadioFeed(BaseModel):
    """A feed the newsroom reads: the catalogue's, or a listener's own site.

    Attributes:
        owner_id: The listener who added it; ``None`` for a catalogue feed.
        url: The feed's address.
        outlet: How the station names its source.
        language: Its language, when known.
        full_text: Whether articles may be fetched whole.
        paused: Whether its listener paused it — their own site only: the
            newsroom stops reading it and no session is offered its stories.
        kind: What it holds (``FeedKind``): a feed read, or a listener's
            interest stories.
        etag: The last reading's validator.
        last_modified: The last reading's validator.
        last_read_at: When it was last read (``None``: never).
        last_status: How that reading ended.
        failures: Readings failed in a row.
    """

    __tablename__ = "radio_feeds"

    owner_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        comment=OWNER_ID_COMMENT,
    )
    url: Mapped[str] = mapped_column(String(URL_MAX_BYTES), nullable=False)
    outlet: Mapped[str] = mapped_column(
        String(OUTLET_MAX_CHARS), nullable=False, comment=OUTLET_COMMENT
    )
    language: Mapped[str | None] = mapped_column(
        String(LANGUAGE_TAG_MAX_CHARS), nullable=True, comment=LANGUAGE_COMMENT
    )
    full_text: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), comment=FULL_TEXT_COMMENT
    )
    etag: Mapped[str | None] = mapped_column(String(ETAG_MAX_CHARS), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(
        String(LAST_MODIFIED_MAX_CHARS), nullable=True
    )
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, comment=LAST_STATUS_COMMENT
    )
    failures: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment=FAILURES_COMMENT
    )
    paused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), comment=PAUSED_COMMENT
    )
    kind: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'source'"), comment=KIND_COMMENT
    )

    __table_args__ = (
        # A catalogue feed is synchronised by its address: one row per address.
        Index(
            "uq_radio_feeds_catalogue_url",
            "url",
            unique=True,
            postgresql_where=text("owner_id IS NULL"),
        ),
        # A listener adds a site once; two listeners may add the same site.
        Index(
            "uq_radio_feeds_owner_url",
            "owner_id",
            "url",
            unique=True,
            postgresql_where=text("owner_id IS NOT NULL"),
        ),
    )


class RadioNewsItem(BaseModel):
    """A story read from a feed.

    Attributes:
        feed_id: Its feed (``CASCADE``: a removed site takes its stories).
        item_key: Its identity within the feed.
        url: The article.
        title: The headline.
        summary: The feed's summary (may be empty).
        published_at: When it was published (never later than when it was read).
        fingerprint: The same story across outlets.
        full_text: The article's text, when read.
        text_state: Where the full text stands (``TextState``).
        text_attempts: Attempts at the full text so far.
        outlet: The outlet that published it, when it is not its feed's (a
            story a search found for the listener's interests).
    """

    __tablename__ = "radio_news_items"

    feed_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("radio_feeds.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_key: Mapped[str] = mapped_column(String(512), nullable=False, comment=ITEM_KEY_COMMENT)
    url: Mapped[str] = mapped_column(String(URL_MAX_BYTES), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fingerprint: Mapped[str] = mapped_column(
        String(200), nullable=False, comment=FINGERPRINT_COMMENT
    )
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_state: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'none'"), comment=TEXT_STATE_COMMENT
    )
    text_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    outlet: Mapped[str | None] = mapped_column(
        String(OUTLET_MAX_CHARS), nullable=True, comment=ITEM_OUTLET_COMMENT
    )

    __table_args__ = (
        Index("uq_radio_news_items_feed_key", "feed_id", "item_key", unique=True),
        # The desk reads the freshest stories; the purge reads the oldest.
        Index("ix_radio_news_items_published", text("published_at DESC")),
        # The collector's text queue: pending articles, newest first.
        Index(
            "ix_radio_news_items_text_pending",
            text("published_at DESC"),
            postgresql_where=text("text_state = 'pending'"),
        ),
    )


__all__ = ["FeedKind", "RadioFeed", "RadioNewsItem", "RadioPreferencesRow", "TextState"]
