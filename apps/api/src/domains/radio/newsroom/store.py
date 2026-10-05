"""The newsroom's database: the feeds it reads and the stories it keeps (ADR-324).

The collector calls this store from concurrent tasks — one per feed, one per
outlet's articles — so every method opens its own short session: an
``AsyncSession`` is never shared across tasks, and none is held open around
the network (ADR-304): the collector reads a feed BETWEEN two calls, never
inside one. Writes use atomic SQL: a failure count grows by column arithmetic,
a story already known is skipped by its unique key, never by a read followed
by a write. Large feeds are inserted in batches within one transaction.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, delete, exists, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.domains.radio.models import (
    FeedKind,
    RadioFeed,
    RadioNewsItem,
    RadioPreferencesRow,
    TextState,
)
from src.domains.radio.newsroom.catalogue import CatalogueFeed
from src.domains.radio.newsroom.collector import FeedReading, FeedState, TextJob
from src.domains.radio.newsroom.editorial_rows import editorial_rows
from src.domains.radio.newsroom.parse import ParsedItem
from src.domains.shared.commercial_content import is_commercial_content
from src.infrastructure.database.session import get_db_context

_ITEM_INSERT_BATCH_SIZE = 500


class NewsroomDatabase:
    """The collector's ``NewsroomStore`` on PostgreSQL."""

    async def sync_catalogue(self, feeds: Sequence[CatalogueFeed]) -> None:
        """Make the stored catalogue the shipped one: added, updated, removed.

        A catalogue feed is identified by its address, and rewritten only when
        what ships differs (a pass runs every few minutes: an unchanged row is
        never rewritten). One no longer shipped is deleted with its stories; a
        listener's own site (it has an owner) is never touched.

        Args:
            feeds: The shipped catalogue.
        """
        now = datetime.now(UTC)
        async with get_db_context() as db:
            if feeds:
                stmt = pg_insert(RadioFeed).values(
                    [
                        {
                            "id": uuid.uuid4(),
                            "owner_id": None,
                            "url": feed.url,
                            "outlet": feed.outlet,
                            "language": feed.language,
                            "full_text": feed.full_text,
                            "failures": 0,
                            "created_at": now,
                            "updated_at": now,
                        }
                        for feed in feeds
                    ]
                )
                await db.execute(
                    stmt.on_conflict_do_update(
                        index_elements=[RadioFeed.url],
                        index_where=RadioFeed.owner_id.is_(None),
                        set_={
                            "outlet": stmt.excluded.outlet,
                            "language": stmt.excluded.language,
                            "full_text": stmt.excluded.full_text,
                            "updated_at": now,
                        },
                        where=or_(
                            RadioFeed.outlet.is_distinct_from(stmt.excluded.outlet),
                            RadioFeed.language.is_distinct_from(stmt.excluded.language),
                            RadioFeed.full_text.is_distinct_from(stmt.excluded.full_text),
                        ),
                    )
                )
            await db.execute(
                delete(RadioFeed).where(
                    RadioFeed.owner_id.is_(None),
                    RadioFeed.url.not_in([feed.url for feed in feeds]),
                )
            )

    async def feed_states(self, *, listened_since: datetime) -> list[FeedState]:
        """The feeds read for someone: the catalogue while anyone listened since
        the instant, a listener's own sites while they did — never a site they paused,
        never the row of the stories a search found for their interests.

        Args:
            listened_since: The start of the listeners' window.
        """
        listeners = select(RadioPreferencesRow.user_id).where(
            RadioPreferencesRow.last_listened_at >= listened_since
        )
        wanted = and_(
            # A listener's interest row holds what a search found: nothing to read.
            RadioFeed.kind == FeedKind.SOURCE.value,
            or_(
                and_(RadioFeed.owner_id.is_(None), exists(listeners)),
                and_(RadioFeed.owner_id.in_(listeners), RadioFeed.paused.is_(False)),
            ),
        )
        async with get_db_context() as db:
            rows = (
                await db.execute(
                    select(
                        RadioFeed.id,
                        RadioFeed.url,
                        RadioFeed.full_text,
                        RadioFeed.etag,
                        RadioFeed.last_modified,
                        RadioFeed.last_read_at,
                        RadioFeed.failures,
                    )
                    .where(wanted)
                    .order_by(RadioFeed.id)
                )
            ).all()
        return [
            FeedState(
                feed_id=row.id,
                url=row.url,
                full_text=row.full_text,
                etag=row.etag,
                last_modified=row.last_modified,
                last_read_at=row.last_read_at,
                failures=row.failures,
            )
            for row in rows
        ]

    async def record_reading(
        self, feed_id: uuid.UUID, reading: FeedReading, *, now: datetime
    ) -> None:
        """File a reading: its status, its validators when it answered, its failure count.

        Args:
            feed_id: The feed read.
            reading: How the reading ended.
            now: When it was read.
        """
        values: dict[str, Any] = {
            "last_read_at": now,
            "last_status": reading.status,
            "updated_at": now,
        }
        if reading.succeeded:
            values |= {"failures": 0, "etag": reading.etag, "last_modified": reading.last_modified}
        else:
            values["failures"] = RadioFeed.failures + 1
        async with get_db_context() as db:
            await db.execute(update(RadioFeed).where(RadioFeed.id == feed_id).values(**values))

    async def add_items(
        self, feed_id: uuid.UUID, items: Sequence[ParsedItem], *, full_text: bool
    ) -> int:
        """Keep the stories not already known; return how many were new.

        Args:
            feed_id: Their feed.
            items: The stories its body held.
            full_text: Whether their articles are worth opening.

        Returns:
            How many were stored (a story already known is skipped).
        """
        if not items:
            return 0
        now = datetime.now(UTC)
        state = TextState.PENDING if full_text else TextState.NONE
        added = 0
        async with get_db_context() as db:
            for start in range(0, len(items), _ITEM_INSERT_BATCH_SIZE):
                batch = items[start : start + _ITEM_INSERT_BATCH_SIZE]
                insert_stmt = pg_insert(RadioNewsItem).values(
                    [
                        {
                            "id": uuid.uuid4(),
                            "feed_id": feed_id,
                            "item_key": item.item_key,
                            "url": item.url,
                            "title": item.title,
                            "summary": item.summary,
                            "published_at": item.published_at,
                            "fingerprint": item.fingerprint,
                            "text_state": state.value,
                            "text_attempts": 0,
                            "created_at": now,
                            "updated_at": now,
                        }
                        for item in batch
                    ]
                )
                stmt = insert_stmt.on_conflict_do_nothing(
                    index_elements=[RadioNewsItem.feed_id, RadioNewsItem.item_key]
                ).returning(RadioNewsItem.id)
                added += len((await db.execute(stmt)).all())
        return added

    async def text_jobs(self, *, limit: int) -> list[TextJob]:
        """Articles waiting to be read, the newest first."""
        async with get_db_context() as db:
            rows = await editorial_rows(
                db,
                select(
                    RadioNewsItem.id,
                    RadioNewsItem.url,
                    RadioNewsItem.text_attempts,
                    RadioNewsItem.title,
                    RadioNewsItem.summary,
                )
                .where(RadioNewsItem.text_state == TextState.PENDING.value)
                .order_by(RadioNewsItem.published_at.desc(), RadioNewsItem.id.desc()),
                limit=limit,
                eligible=lambda row: not is_commercial_content(row.title, summary=row.summary),
                identity=lambda row: row.id,
            )
        return [TextJob(item_id=row.id, url=row.url, attempts=row.text_attempts) for row in rows]

    async def record_text(self, item_id: uuid.UUID, text: str | None, *, final: bool) -> None:
        """File an article's text; ``None`` and not final means « try again later ».

        Args:
            item_id: The story.
            text: Its article's text, when it could be read.
            final: Whether no further attempt will be made.
        """
        values: dict[str, Any] = {
            "text_attempts": RadioNewsItem.text_attempts + 1,
            "updated_at": datetime.now(UTC),
        }
        if text is not None:
            values |= {"full_text": text, "text_state": TextState.READY.value}
        elif final:
            values["text_state"] = TextState.UNAVAILABLE.value
        async with get_db_context() as db:
            await db.execute(
                update(RadioNewsItem).where(RadioNewsItem.id == item_id).values(**values)
            )

    async def purge(self, *, published_before: datetime) -> int:
        """Remove the stories published before an instant; return how many."""
        async with get_db_context() as db:
            result = await db.execute(
                delete(RadioNewsItem)
                .where(RadioNewsItem.published_at < published_before)
                .returning(RadioNewsItem.id)
            )
            return len(result.all())


__all__ = ["NewsroomDatabase"]
